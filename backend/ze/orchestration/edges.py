from ze.capability.types import GateDecision
from ze.orchestration.state import AgentState


def after_embed_route(state: AgentState) -> str:
    envelope = state.get("envelope")
    if envelope and envelope.is_compound:
        return "decompose"
    return "fetch_context"


def after_capability_check(state: AgentState) -> str:
    decision = state.get("gate_decision")
    match decision:
        case GateDecision.EXECUTE:
            return "execute_tool"
        case GateDecision.DRAFT:
            return "draft_response"
        case GateDecision.AWAIT_CONFIRMATION:
            return "draft_response"
        case GateDecision.BLOCKED:
            return "end_blocked"
        case _:
            return "end_blocked"


def after_execute_tool(state: AgentState) -> str:
    if state.get("subtask_results"):
        return "synthesize"
    return "write_memory"
