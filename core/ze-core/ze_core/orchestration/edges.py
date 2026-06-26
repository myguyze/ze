from __future__ import annotations

from ze_agents.types import GateDecision
from ze_core.orchestration.state import AgentState


def after_embed_route(state: AgentState) -> str:
    envelope = state["envelope"]
    if envelope and envelope.is_compound:
        return "decompose"
    return "fetch_context"


def after_decompose(state: AgentState) -> str:
    """Sequential compound tasks need WorkflowPlanner before fetch_context."""
    envelope = state.get("envelope")
    if envelope and envelope.is_sequential:
        return "plan_sequential"
    return "fetch_context"


def after_capability_check(state: AgentState) -> str:
    match state["gate_decision"]:
        case GateDecision.EXECUTE:
            return "execute_tool"
        case GateDecision.DRAFT | GateDecision.AWAIT_CONFIRMATION:
            return "draft_response"
        case _:
            return "end_blocked"


def after_execute_tool(state: AgentState) -> str:
    return "correlate"


def after_correlate(state: AgentState) -> str:
    envelope = state.get("envelope")
    if envelope and envelope.is_compound and state.get("subtask_results"):
        return "synthesize"
    return "record_trace"


def after_await_confirmation(state: AgentState) -> str:
    """Route to record_trace when the draft IS the final response (DRAFT_ONLY ceiling).
    Otherwise route to execute_tool to perform the approved action."""
    if state.get("final_response"):
        return "record_trace"
    return "execute_tool"


