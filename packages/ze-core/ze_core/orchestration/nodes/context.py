from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from ze_core.logging import get_logger
from ze_core.memory.types import MemoryContext
from ze_core.orchestration.state import AgentState
from ze_core.orchestration.types import AgentContext

log = get_logger(__name__)

SESSION_HISTORY_LIMIT = 10
_DEFAULT_INACTIVITY_MINUTES = 30


async def fetch_context(state: AgentState, config: RunnableConfig) -> dict:
    store: Any = config["configurable"]["memory_store"]
    embedder: Any = config["configurable"]["embedder"]
    cfg: Any = config["configurable"].get("settings")

    inactivity_minutes = _DEFAULT_INACTIVITY_MINUTES
    if cfg is not None:
        inactivity_minutes = getattr(cfg, "session_inactivity_minutes", None) or (
            cfg.get("session_inactivity_minutes", _DEFAULT_INACTIVITY_MINUTES)
            if isinstance(cfg, dict) else _DEFAULT_INACTIVITY_MINUTES
        )

    persona_store: Any = config["configurable"].get("persona_store")
    person_store: Any = config["configurable"].get("person_store")

    envelope = state.get("envelope")
    agent_name = (
        envelope.subtasks[0].agent if envelope and envelope.subtasks else "global"
    )
    intent = (
        envelope.subtasks[0].intent if envelope and envelope.subtasks else "read"
    )

    embed_text = state.get("image_caption") or state["prompt"]
    prompt_embedding = embedder.encode(embed_text)

    memory_context: MemoryContext = await store.get_context(
        prompt_embedding=prompt_embedding,
        agent=agent_name,
    )

    active_persona: dict = {}
    if persona_store is not None:
        active_persona = await persona_store.get_active() or {}

    now = time.time()
    last_active = state.get("last_active_at")
    if last_active and (now - last_active) > (inactivity_minutes * 60):
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

    contact_context: Any = None
    if person_store is not None:
        contact_context = await person_store.get_context(prompt_for_ctx)

    agent_context = AgentContext(
        session_id=state["session_id"],
        prompt=prompt_for_ctx,
        intent=intent,
        memory=memory_context,
        contacts=contact_context,
        messages=messages,
        persona=active_persona,
    )

    return {
        "memory_context": memory_context,
        "agent_context": agent_context,
        "last_active_at": now,
    }
