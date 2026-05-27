import time

from langchain_core.runnables import RunnableConfig
from sentence_transformers import SentenceTransformer

from ze.agents.types import AgentContext
from ze.contacts.store import PersonStore
from ze.contacts.types import PersonContext
from ze.logging import get_logger
from ze_core.memory.postgres import PostgresMemoryStore as MemoryStore
from ze.orchestration.state import AgentState
from ze_core.persona.postgres import PostgresPersonaStore as PersonaStore
from ze.settings import Settings
from ze_core.telemetry.context import set_agent_context

log = get_logger(__name__)

_SESSION_HISTORY_LIMIT = 10


async def fetch_context(state: AgentState, config: RunnableConfig) -> dict:
    """Encode the prompt, load memory context, and build the AgentContext."""
    set_agent_context("memory_store")
    store: MemoryStore = config["configurable"]["memory_store"]
    persona_store: PersonaStore = config["configurable"]["persona_store"]
    person_store: PersonStore | None = config["configurable"].get("person_store")
    embedder: SentenceTransformer = config["configurable"]["embedder"]
    settings: Settings = config["configurable"]["settings"]
    envelope = state["envelope"]
    agent = (
        envelope.subtasks[0].agent
        if envelope and envelope.subtasks
        else "global"
    )

    embed_text = state.get("image_caption") or state["prompt"]
    prompt_embedding = embedder.encode(embed_text)
    memory_context = await store.get_context(
        prompt_embedding=prompt_embedding,
        agent=agent,
    )
    active_persona = await persona_store.get_active()

    # Clear history if the session has been inactive too long.
    now = time.time()
    last_active = state.get("last_active_at")
    inactivity_limit = settings.session_inactivity_minutes * 60
    if last_active and (now - last_active) > inactivity_limit:
        history: list[dict] = []
        log.info("session_expired", session_id=state["session_id"])
    else:
        history = list(state.get("messages") or [])

    if state.get("input_modality") == "image":
        user_text = state.get("image_caption") or state.get("prompt") or "(image)"
    else:
        user_text = state["prompt"]
    messages = history + [{"role": "user", "content": user_text}]

    prompt_for_ctx = state.get("image_caption") or state["prompt"]

    contact_context = PersonContext()
    if person_store:
        contact_context = await person_store.get_context(prompt_for_ctx)

    agent_context = AgentContext(
        session_id=state["session_id"],
        prompt=prompt_for_ctx,
        intent=envelope.subtasks[0].intent if envelope and envelope.subtasks else "read",
        memory=memory_context,
        contacts=contact_context,
        messages=messages,
        persona=active_persona,
        # reporter is intentionally omitted — ProgressReporter is not serializable and
        # must not be stored in AgentState. execution.py injects it from config directly.
    )

    log.debug(
        "orchestration_context_fetched",
        session_id=state["session_id"],
        fact_count=len(memory_context.facts),
        episode_count=len(memory_context.episodes),
        contact_count=len(contact_context.people),
        history_len=len(history),
    )

    return {
        "memory_context": memory_context,
        "agent_context": agent_context,
        "last_active_at": now,
    }
