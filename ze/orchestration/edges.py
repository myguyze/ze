from ze.capability.types import GateDecision
from ze.orchestration.state import AgentState


def after_embed_route(state: AgentState) -> str:
    envelope = state.get("envelope")
    if envelope and envelope.is_compound:
        if envelope.is_sequential:
            return "plan_sequential"
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
    envelope = state.get("envelope")
    if envelope and envelope.is_compound and state.get("subtask_results"):
        return "synthesize"
    return "write_memory"


# ── Workflow graph edges ───────────────────────────────────────────────────────

def after_capability_check_workflow(state: AgentState) -> str:
    """In workflow mode all steps execute directly — the workflow creation was the gate."""
    decision = state.get("gate_decision")
    if decision == GateDecision.BLOCKED:
        return "workflow_failed"
    return "execute_tool"


def after_verify_step(state: AgentState) -> str:
    step_results = state.get("workflow_step_results") or []
    if step_results and not step_results[-1].success:
        return "workflow_failed"
    steps = state.get("workflow_steps") or []
    if state.get("current_step_index", 0) >= len(steps):
        return "workflow_synthesize"
    return "load_workflow_step"
