from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from ze_core.orchestration.nodes.correlation import correlate, _inline_config, _build_component, _format_text_section
from ze_memory.types import Entity, MemoryContext
from ze_core.routing.types import RoutingEnvelope, SubTask


UTC = timezone.utc

# ── Minimal Hypothesis / EvidenceRef stubs ────────────────────────────────────

@dataclass
class _EvidenceRef:
    kind: str = "signal"
    id: UUID = field(default_factory=uuid4)
    label: str = "Signal A (Jun 12)"
    external_ref: str | None = "https://example.com/a"
    origin: str = "graph_recall"
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    ingested_at: datetime | None = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _Hypothesis:
    id: UUID = field(default_factory=uuid4)
    summary: str = "Possible link between A and B"
    narrative: str = "A and B overlap in timing"
    relation: str = "pattern"
    confidence: float = 0.8
    relevance: float = 0.6
    evidence: list = field(default_factory=lambda: [_EvidenceRef(), _EvidenceRef(label="Signal B (Jun 14)")])
    entities: list = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    surfaced: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _envelope(agent: str = "research", is_compound: bool = False) -> RoutingEnvelope:
    st = SubTask(agent=agent, intent="read", prompt="news on Anthropic")
    return RoutingEnvelope(
        primary_agent=agent,
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=[st],
        requires_synthesis=False,
    )


def _memory_ctx(entity_ids: list[UUID] | None = None) -> MemoryContext:
    ids = entity_ids or [uuid4()]
    entities = [
        Entity(id=eid, entity_type="org", canonical_name=f"Entity-{i}")
        for i, eid in enumerate(ids)
    ]
    return MemoryContext(entities=entities)


def _engine(hypotheses: list | None = None) -> MagicMock:
    eng = AsyncMock()
    eng.correlate = AsyncMock(return_value=[_Hypothesis()] if hypotheses is None else hypotheses)
    return eng


def _config(
    engine: Any = None,
    agent: str = "research",
    settings: dict | None = None,
) -> dict:
    return {
        "configurable": {
            "correlation_engine": engine,
            "settings": settings or {
                "correlation": {
                    "inline": {"timeout_ms": 1500, "max_connections_shown": 2, "agents": ["research", "news"]},
                    "salience": {"surfacing": {"tau_inline": 0.45}},
                }
            },
        }
    }


def _state(
    agent: str = "research",
    memory_ctx: MemoryContext | None = None,
    components: list | None = None,
    subtask_results: list | None = None,
    agent_result: Any = None,
) -> dict:
    from ze_agents.types import AgentResult
    return {
        "envelope": _envelope(agent),
        "memory_context": memory_ctx or _memory_ctx(),
        "components": components or [],
        "subtask_results": subtask_results or [],
        "agent_result": agent_result or AgentResult(agent=agent, response="Main answer."),
        "session_id": "s1",
        "correlations": [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_yields_correlations_and_component_for_qualifying_turn():
    eng = _engine()
    result = await correlate(_state(), _config(engine=eng))

    assert result["correlations"]
    assert len(result["components"]) == 1
    assert result["components"][0]["type"] == "connections"
    eng.correlate.assert_awaited_once()


async def test_single_agent_sets_final_response_with_section():
    eng = _engine()
    result = await correlate(_state(), _config(engine=eng))

    assert "final_response" in result
    assert "Connected to your history" in result["final_response"]
    assert "Main answer." in result["final_response"]


async def test_no_engine_configured_returns_empty():
    result = await correlate(_state(), _config(engine=None))
    assert result == {}


async def test_non_qualifying_agent_skips_correlation():
    eng = _engine()
    result = await correlate(_state(agent="companion"), _config(engine=eng))
    assert result == {}
    eng.correlate.assert_not_awaited()


async def test_no_entities_in_memory_context_skips_correlation():
    eng = _engine()
    ctx = MemoryContext(entities=[])
    result = await correlate(_state(memory_ctx=ctx), _config(engine=eng))
    assert result == {}
    eng.correlate.assert_not_awaited()


async def test_entities_without_ids_skips_correlation():
    eng = _engine()
    ctx = MemoryContext(entities=[Entity(id=None, entity_type="org", canonical_name="Anon")])
    result = await correlate(_state(memory_ctx=ctx), _config(engine=eng))
    assert result == {}


async def test_engine_returns_empty_yields_no_update():
    eng = _engine(hypotheses=[])
    result = await correlate(_state(), _config(engine=eng))
    assert result == {}


async def test_low_confidence_hypothesis_filtered_out():
    h = _Hypothesis(confidence=0.3)  # below tau_inline=0.45
    eng = _engine(hypotheses=[h])
    result = await correlate(_state(), _config(engine=eng))
    assert result == {}


async def test_max_connections_shown_limits_output():
    hypotheses = [_Hypothesis(confidence=0.9) for _ in range(5)]
    eng = _engine(hypotheses=hypotheses)
    result = await correlate(_state(), _config(engine=eng))
    assert len(result["correlations"]) == 2  # max_connections_shown=2


async def test_timeout_drops_section_silently():
    async def _slow(*args, **kwargs):
        await asyncio.sleep(10)
        return [_Hypothesis()]

    eng = MagicMock()
    eng.correlate = _slow

    cfg = _config(engine=eng, settings={
        "correlation": {
            "inline": {"timeout_ms": 50, "max_connections_shown": 2, "agents": ["research", "news"]},
            "salience": {"surfacing": {"tau_inline": 0.45}},
        }
    })
    result = await correlate(_state(), cfg)
    assert result == {}


async def test_engine_error_drops_section_silently():
    eng = AsyncMock()
    eng.correlate = AsyncMock(side_effect=RuntimeError("boom"))
    result = await correlate(_state(), _config(engine=eng))
    assert result == {}


async def test_existing_components_are_preserved():
    eng = _engine()
    existing = [{"type": "card", "body": "existing"}]
    result = await correlate(_state(components=existing), _config(engine=eng))
    assert result["components"][0]["type"] == "card"
    assert result["components"][1]["type"] == "connections"


async def test_compound_turn_does_not_set_final_response():
    from ze_agents.types import AgentResult
    eng = _engine()
    subtask_results = [AgentResult(agent="research", response="data")]
    st1 = SubTask(agent="research", intent="read", prompt="hi")
    st2 = SubTask(agent="news", intent="read", prompt="hi")
    compound_envelope = RoutingEnvelope(
        primary_agent="research",
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=True,
        subtasks=[st1, st2],
        requires_synthesis=True,
    )
    state = {
        "envelope": compound_envelope,
        "memory_context": _memory_ctx(),
        "components": [],
        "subtask_results": subtask_results,
        "agent_result": None,
        "session_id": "s1",
        "correlations": [],
    }
    result = await correlate(state, _config(engine=eng))
    assert "final_response" not in result
    assert result["correlations"]


# ── Unit tests for helpers ─────────────────────────────────────────────────────

def test_inline_config_reads_from_dict_settings():
    settings = {
        "correlation": {
            "inline": {"timeout_ms": 999, "max_connections_shown": 3, "agents": ["news"]},
            "salience": {"surfacing": {"tau_inline": 0.55}},
        }
    }
    cfg = _inline_config(settings)
    assert cfg["timeout_ms"] == 999
    assert cfg["max_connections_shown"] == 3
    assert cfg["agents"] == ["news"]
    assert cfg["tau_inline"] == 0.55


def test_inline_config_uses_defaults_when_missing():
    cfg = _inline_config(None)
    assert cfg["tau_inline"] == 0.45
    assert cfg["timeout_ms"] == 1500
    assert cfg["max_connections_shown"] == 2
    assert "research" in cfg["agents"]


def test_build_component_structure():
    h = _Hypothesis()
    component = _build_component([h])
    assert component["type"] == "connections"
    assert component["title"] == "Connected to your history"
    assert len(component["connections"]) == 1
    conn = component["connections"][0]
    assert conn["summary"] == h.summary
    assert conn["relation"] == "pattern"
    assert len(conn["evidence"]) == 2


def test_format_text_section_contains_summary():
    h = _Hypothesis()
    text = _format_text_section([h])
    assert "Connected to your history" in text
    assert h.summary in text
