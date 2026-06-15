"""
Serialization smoke tests for AgentState.

LangGraph checkpoints the entire graph state to Postgres after every node using
JsonPlusSerializer + msgpack. These tests verify that a realistic AgentState —
as produced by fetch_context — survives a full dumps_typed → loads_typed
round-trip with the same serde configuration used in production.

A failure here means the app will crash at checkpoint time, not at startup,
which makes it hard to catch without exercising the full flow in dev.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import pytest

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer  # type: ignore[import]

from ze_agents.types import GateDecision
from ze_memory.types import Episode, Fact, MemoryContext, ProfileFacet
from ze_agents.types import AgentContext, AgentResult, ToolCall
from ze_core.checkpoint_serde import build_checkpoint_serde
from ze_core.routing.types import RoutingEnvelope, SubTask


# ── Serde fixture ─────────────────────────────────────────────────────────────

@pytest.fixture
def serde() -> JsonPlusSerializer:
    return build_checkpoint_serde(plugins=[])


# ── Builders for realistic domain objects ─────────────────────────────────────

def _make_memory_context() -> MemoryContext:
    return MemoryContext(
        facts=[
            Fact(
                id=UUID("12345678-1234-5678-1234-567812345678"),
                subject_id=None,
                predicate="name",
                object_text=None,
                object_id=None,
                value="João",
                confidence=0.9,
                reviewed=True,
                embedding=None,
            )
        ],
        episodes=[
            Episode(
                id=UUID("87654321-4321-8765-4321-876543218765"),
                session_id="test-session",
                agent="research",
                prompt="what is the weather?",
                response="It is sunny.",
                summary="Weather query",
                relevance=0.7,
                created_at=datetime(2024, 1, 2, tzinfo=timezone.utc),
                embedding=None,  # must be None in stored state
            )
        ],
        token_estimate=120,
        profile=[
            ProfileFacet(
                key="preferences",
                value="concise replies",
                stability="stable",
                confidence=0.9,
                updated_at=datetime(2024, 1, 3, tzinfo=timezone.utc),
            )
        ],
    )


def _make_agent_context() -> AgentContext:
    return AgentContext(
        session_id="test-session",
        prompt="what is on my calendar today?",
        intent="read",
        gate_decision=GateDecision.EXECUTE,
        memory=_make_memory_context(),
        contacts=None,
        tool_calls=[
            ToolCall(
                tool_name="get_events",
                args={"date": "today"},
                result=[{"title": "standup"}],
                duration_ms=120,
                success=True,
            )
        ],
        messages=[{"role": "user", "content": "what is on my calendar today?"}],
        persona={"humor": 5, "verbosity": 3},
        model="openai/gpt-4o-mini",
        reporter=None,       # never serialized; must stay None in stored state
        extensions={},       # functions must never be stored here
    )


def _make_envelope() -> RoutingEnvelope:
    return RoutingEnvelope(
        primary_agent="calendar",
        confidence=0.92,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=False,
        subtasks=[SubTask(agent="calendar", intent="read", prompt="what is on my calendar today?")],
        requires_synthesis=False,
        raw_scores={"calendar": 0.92, "research": 0.62},
    )


def _make_agent_result() -> AgentResult:
    return AgentResult(
        agent="calendar",
        response="You have a standup at 10am.",
        tool_calls=[
            ToolCall(
                tool_name="get_events",
                args={"date": "today"},
                result=[{"title": "standup", "time": "10:00"}],
                duration_ms=85,
                success=True,
            )
        ],
        tokens_used=340,
    )


# ── Round-trip helpers ────────────────────────────────────────────────────────

def round_trip(serde: JsonPlusSerializer, obj: object) -> object:
    type_, data = serde.dumps_typed(obj)
    return serde.loads_typed((type_, data))


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_memory_context_round_trips(serde: JsonPlusSerializer) -> None:
    original = _make_memory_context()
    restored = round_trip(serde, original)
    assert restored.token_estimate == original.token_estimate
    assert restored.facts[0].predicate == "name"
    assert restored.facts[0].id == original.facts[0].id
    assert restored.episodes[0].agent == "research"
    assert restored.profile[0].key == "preferences"


def test_agent_context_round_trips(serde: JsonPlusSerializer) -> None:
    original = _make_agent_context()
    restored = round_trip(serde, original)
    assert restored.session_id == original.session_id
    assert restored.prompt == original.prompt
    assert restored.gate_decision == GateDecision.EXECUTE
    assert restored.memory.facts[0].predicate == "name"
    assert restored.tool_calls[0].tool_name == "get_events"
    assert restored.extensions == {}
    assert restored.reporter is None


def test_routing_envelope_round_trips(serde: JsonPlusSerializer) -> None:
    original = _make_envelope()
    restored = round_trip(serde, original)
    assert restored.primary_agent == "calendar"
    assert restored.subtasks[0].agent == "calendar"
    assert restored.raw_scores["calendar"] == pytest.approx(0.92)


def test_agent_result_round_trips(serde: JsonPlusSerializer) -> None:
    original = _make_agent_result()
    restored = round_trip(serde, original)
    assert restored.agent == "calendar"
    assert restored.tokens_used == 340
    assert restored.tool_calls[0].success is True


def test_gate_decision_round_trips(serde: JsonPlusSerializer) -> None:
    for decision in GateDecision:
        assert round_trip(serde, decision) == decision


def test_full_agent_state_dict_round_trips(serde: JsonPlusSerializer) -> None:
    """Mirrors what LangGraph checkpoints: the entire state dict value by value."""
    state = {
        "prompt": "what is on my calendar today?",
        "session_id": "test-session",
        "session_overrides": {},
        "input_modality": "text",
        "audio_data": None,
        "audio_mime": None,
        "image_data": None,
        "image_mime": None,
        "image_caption": None,
        "envelope": _make_envelope(),
        "memory_context": _make_memory_context(),
        "agent_context": _make_agent_context(),
        "gate_decision": GateDecision.EXECUTE,
        "agent_result": _make_agent_result(),
        "subtask_results": [_make_agent_result()],
        "pending_confirmation": False,
        "messages": [{"role": "user", "content": "what is on my calendar today?"}],
        "last_active_at": 1_700_000_000.0,
        "final_response": "You have a standup at 10am.",
        "error": None,
        "dynamic_plan_steps": None,
        "dynamic_plan_high_risk": [],
    }

    for key, value in state.items():
        try:
            restored = round_trip(serde, value)
        except Exception as exc:
            pytest.fail(f"State field {key!r} failed serde round-trip: {exc}")

        assert restored == value or restored is value, (
            f"State field {key!r} did not survive round-trip: {value!r} → {restored!r}"
        )


def test_non_serializable_embed_fn_raises(serde: JsonPlusSerializer) -> None:
    ctx = AgentContext(
        session_id="s",
        prompt="p",
        intent="read",
        embed_fn=lambda _text: [0.1],
    )
    with pytest.raises((TypeError, Exception)):
        serde.dumps_typed(ctx)


def test_non_serializable_identity_builder_raises(serde: JsonPlusSerializer) -> None:
    """Regression: AgentContext with identity_builder set must not be checkpointed.

    identity_builder is a runtime-only callable. Stored contexts always have it
    as None. If someone accidentally checkpoints a context with it set, the serde
    must fail loudly here in CI rather than at runtime in production.
    """
    def _some_builder(persona: dict, memory_context: str, *, profile: Any, contacts_context: str) -> str:
        return "identity"

    ctx = AgentContext(
        session_id="s",
        prompt="p",
        intent="read",
        identity_builder=_some_builder,
    )
    with pytest.raises((TypeError, Exception)):
        serde.dumps_typed(ctx)
