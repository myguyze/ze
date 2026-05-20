import time

from langchain_core.runnables import RunnableConfig
from sentence_transformers import SentenceTransformer

from ze.agents.types import AgentContext
from ze.logging import get_logger
from ze.memory.store import MemoryStore
from ze.orchestration.state import AgentState
from ze.settings import Settings
from ze.telemetry.context import set_agent_context

log = get_logger(__name__)

_SESSION_HISTORY_LIMIT = 10


async def fetch_context(state: AgentState, config: RunnableConfig) -> dict:
    """Encode the prompt, load memory context, and build the AgentContext."""
    set_agent_context("memory_store")
    store: MemoryStore = config["configurable"]["memory_store"]
    embedder: SentenceTransformer = config["configurable"]["embedder"]
    settings: Settings = config["configurable"]["settings"]
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

    # Clear history if the session has been inactive too long.
    now = time.time()
    last_active = state.get("last_active_at")
    inactivity_limit = settings.session_inactivity_minutes * 60
    if last_active and (now - last_active) > inactivity_limit:
        history: list[dict] = []
        log.info("session_expired", session_id=state["session_id"])
    else:
        history = list(state.get("messages") or [])

    messages = history + [{"role": "user", "content": state["prompt"]}]

    agent_context = AgentContext(
        session_id=state["session_id"],
        prompt=state["prompt"],
        intent=envelope.subtasks[0].intent if envelope and envelope.subtasks else "read",
        memory=memory_context,
        messages=messages,
    )

    log.debug(
        "orchestration_context_fetched",
        session_id=state["session_id"],
        fact_count=len(memory_context.facts),
        episode_count=len(memory_context.episodes),
        history_len=len(history),
    )

    return {
        "memory_context": memory_context,
        "agent_context": agent_context,
        "last_active_at": now,
    }
