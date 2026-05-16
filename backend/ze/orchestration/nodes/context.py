from ze.agents.types import AgentContext
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.state import AgentState

log = get_logger(__name__)


async def fetch_context(state: AgentState, config: dict) -> dict:
    """Load memory context and build the AgentContext passed to the agent."""
    store: MemoryStore = config["configurable"]["memory_store"]
    envelope = state["envelope"]

    memory_context = await store.get_context(
        session_id=state["session_id"],
        prompt=state["prompt"],
    )

    agent_context = AgentContext(
        session_id=state["session_id"],
        prompt=state["prompt"],
        intent=envelope.subtasks[0].intent if envelope and envelope.subtasks else "read",
        memory=memory_context,
    )

    log.debug(
        "orchestration_context_fetched",
        session_id=state["session_id"],
        fact_count=len(memory_context.facts),
        episode_count=len(memory_context.episodes),
    )

    return {
        "memory_context": memory_context,
        "agent_context": agent_context,
    }
