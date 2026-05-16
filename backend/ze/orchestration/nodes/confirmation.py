from ze.logging import get_logger
from ze.orchestration.state import AgentState

log = get_logger(__name__)


async def await_confirmation(state: AgentState, config: dict) -> dict:
    """
    Mark the graph as paused awaiting user confirmation.

    The graph is configured with interrupt_before=["await_confirmation"], so
    LangGraph pauses *before* this node executes and checkpoints state. This node
    runs only after the WebSocket handler resumes execution with a confirm/reject
    message. It simply records that confirmation is pending so downstream edges
    can inspect it.
    """
    log.info(
        "orchestration_awaiting_confirmation",
        session_id=state["session_id"],
        agent=state["envelope"].primary_agent if state.get("envelope") else None,
    )
    return {"pending_confirmation": True}
