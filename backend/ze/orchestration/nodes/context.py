from sentence_transformers import SentenceTransformer

from ze.agents.types import AgentContext
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.state import AgentState

log = get_logger(__name__)


async def fetch_context(state: AgentState, config: dict) -> dict:
    """Encode the prompt, load memory context, and build the AgentContext."""
    store: MemoryStore = config["configurable"]["memory_store"]
    embedder: SentenceTransformer = config["configurable"]["embedder"]
    envelope = state["envelope"]
    agent = (
        envelope.subtasks[0].agent
        if envelope and envelope.subtasks
        else "global"
    )

    prompt_embedding = embedder.encode(state["prompt"])
    memory_context = await store.get_context(
        prompt_embedding=prompt_embedding,
        agent=agent,
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
