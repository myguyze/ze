from langchain_core.runnables import RunnableConfig

from ze.capability.types import GateDecision
from ze.logging import get_logger
from ze.orchestration.state import AgentState

log = get_logger(__name__)


async def await_confirmation(state: AgentState, config: RunnableConfig) -> dict:
    """
    Resume point after the user confirms a write action.

    The graph is configured with interrupt_before=["await_confirmation"], so
    LangGraph pauses *before* this node and checkpoints state. This node only
    runs after the Telegram bot resumes via a callback_query (user confirmed).

    Sets gate_decision=EXECUTE so the downstream execute_tool node performs the
    real write instead of a draft.
    """
    log.info(
        "orchestration_confirmation_received",
        session_id=state["session_id"],
        agent=state["envelope"].primary_agent if state.get("envelope") else None,
    )
    return {"pending_confirmation": False, "gate_decision": GateDecision.EXECUTE}
