import pytest

from ze_core.capability.types import GateDecision
from ze_core.orchestration.edges import (
    after_capability_check,
    after_embed_route,
    after_execute_tool,
)
from ze_core.routing.types import RoutingEnvelope, SubTask


def _envelope(is_compound: bool = False, subtask_results_present: bool = False) -> RoutingEnvelope:
    return RoutingEnvelope(
        primary_agent="a",
        confidence=0.9,
        score_gap=0.3,
        routing_method="embedding",
        is_compound=is_compound,
        subtasks=[SubTask(agent="a", intent="read", prompt="p")],
        requires_synthesis=False,
    )


def _state(**kwargs) -> dict:
    base = {
        "envelope": _envelope(),
        "gate_decision": None,
        "subtask_results": [],
    }
    base.update(kwargs)
    return base


class TestAfterEmbedRoute:
    def test_single_goes_to_fetch_context(self):
        assert after_embed_route(_state(envelope=_envelope(is_compound=False))) == "fetch_context"

    def test_compound_goes_to_decompose(self):
        assert after_embed_route(_state(envelope=_envelope(is_compound=True))) == "decompose"

    def test_none_envelope_goes_to_fetch_context(self):
        assert after_embed_route(_state(envelope=None)) == "fetch_context"


class TestAfterCapabilityCheck:
    def test_execute_routes_to_execute_tool(self):
        assert after_capability_check(_state(gate_decision=GateDecision.EXECUTE)) == "execute_tool"

    def test_draft_routes_to_draft_response(self):
        assert after_capability_check(_state(gate_decision=GateDecision.DRAFT)) == "draft_response"

    def test_await_confirmation_routes_to_draft_response(self):
        assert after_capability_check(_state(gate_decision=GateDecision.AWAIT_CONFIRMATION)) == "draft_response"

    def test_blocked_routes_to_end_blocked(self):
        assert after_capability_check(_state(gate_decision=GateDecision.BLOCKED)) == "end_blocked"

    def test_none_routes_to_end_blocked(self):
        assert after_capability_check(_state(gate_decision=None)) == "end_blocked"


class TestAfterExecuteTool:
    def test_single_task_goes_to_write_memory(self):
        state = _state(envelope=_envelope(is_compound=False), subtask_results=[])
        assert after_execute_tool(state) == "write_memory"

    def test_compound_with_results_goes_to_synthesize(self):
        from ze_core.orchestration.types import AgentResult
        result = AgentResult(agent="a", response="r")
        state = _state(
            envelope=_envelope(is_compound=True),
            subtask_results=[result],
        )
        assert after_execute_tool(state) == "synthesize"

    def test_compound_no_results_goes_to_write_memory(self):
        state = _state(envelope=_envelope(is_compound=True), subtask_results=[])
        assert after_execute_tool(state) == "write_memory"
