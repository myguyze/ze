import pytest

from ze.capability.types import GateDecision
from ze.logging import configure_logging
from ze.orchestration.edges import after_capability_check, after_embed_route, after_execute_tool
from ze.routing.types import RoutingEnvelope, SubTask


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


def make_envelope(is_compound: bool = False, agents=("research",)) -> RoutingEnvelope:
    subtasks = [SubTask(agent=a, intent="read", prompt="hi") for a in agents]
    return RoutingEnvelope(
        primary_agent=subtasks[0].agent,
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=subtasks,
        requires_synthesis=is_compound,
    )


def base_state(**overrides) -> dict:
    defaults: dict = {
        "prompt": "hello",
        "session_id": "s1",
        "session_overrides": {},
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "pending_confirmation": False,
        "final_response": None,
        "error": None,
    }
    defaults.update(overrides)
    return defaults


# ── after_embed_route ─────────────────────────────────────────────────────────

def test_after_embed_route_single_goes_to_fetch_context():
    state = base_state(envelope=make_envelope(is_compound=False))
    assert after_embed_route(state) == "fetch_context"


def test_after_embed_route_compound_goes_to_decompose():
    state = base_state(envelope=make_envelope(is_compound=True, agents=("research", "companion")))
    assert after_embed_route(state) == "decompose"


def test_after_embed_route_none_envelope_goes_to_fetch_context():
    state = base_state(envelope=None)
    assert after_embed_route(state) == "fetch_context"


# ── after_capability_check ────────────────────────────────────────────────────

def test_after_capability_check_execute():
    state = base_state(gate_decision=GateDecision.EXECUTE)
    assert after_capability_check(state) == "execute_tool"


def test_after_capability_check_draft():
    state = base_state(gate_decision=GateDecision.DRAFT)
    assert after_capability_check(state) == "draft_response"


def test_after_capability_check_await_confirmation():
    state = base_state(gate_decision=GateDecision.AWAIT_CONFIRMATION)
    assert after_capability_check(state) == "draft_response"


def test_after_capability_check_blocked():
    state = base_state(gate_decision=GateDecision.BLOCKED)
    assert after_capability_check(state) == "end_blocked"


def test_after_capability_check_none_goes_to_end_blocked():
    state = base_state(gate_decision=None)
    assert after_capability_check(state) == "end_blocked"


# ── after_execute_tool ────────────────────────────────────────────────────────

def test_after_execute_tool_single_goes_to_write_memory():
    state = base_state(subtask_results=[])
    assert after_execute_tool(state) == "write_memory"


def test_after_execute_tool_compound_goes_to_synthesize():
    from ze.agents.types import AgentResult
    results = [AgentResult(agent="research", response="data")]
    state = base_state(subtask_results=results)
    assert after_execute_tool(state) == "synthesize"
