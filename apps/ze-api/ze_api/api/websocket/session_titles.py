from __future__ import annotations

from typing import Any

from ze_agents.model_resolution import resolve_model
from ze_agents.tasks import fire_and_forget
from ze_core.conversation.sessions import SessionTitleGenerator
from ze_logging import get_logger

log = get_logger(__name__)

_DEFAULT_MODEL = "anthropic/claude-haiku-4-5"


def _title_generator(container: Any) -> SessionTitleGenerator:
    model = resolve_model("session_title", _DEFAULT_MODEL, container.settings.config)
    return SessionTitleGenerator(container.openrouter_client, model)


async def _first_user_text(msg_store: Any, thread_id: str) -> str | None:
    messages = await msg_store.list_by_thread(thread_id, limit=50)
    for message in messages:
        if message.role == "user" and message.text:
            return message.text
    return None


async def _generate_and_save(
    container: Any,
    session_store: Any,
    thread_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    session = await session_store.get(thread_id)
    if session is None or session.title_source == "generated":
        return

    try:
        generator = _title_generator(container)
        title = await generator.generate(
            user_text=user_text, assistant_text=assistant_text
        )
        if not title:
            return
        await session_store.upsert(
            thread_id,
            title=title,
            title_source="generated",
            update_title=True,
        )
    except Exception as exc:
        log.warning(
            "session_title_generation_failed", thread_id=thread_id, error=str(exc)
        )


def schedule_session_title(
    container: Any,
    session_store: Any,
    thread_id: str,
    *,
    user_text: str | None,
    assistant_text: str,
) -> None:
    if not user_text or not assistant_text.strip():
        return

    fire_and_forget(
        _generate_and_save(
            container, session_store, thread_id, user_text, assistant_text
        ),
        label="session_title_generation",
    )


async def schedule_session_title_from_thread(
    container: Any,
    session_store: Any,
    msg_store: Any,
    thread_id: str,
    assistant_text: str,
) -> None:
    user_text = await _first_user_text(msg_store, thread_id)
    if not user_text:
        return
    schedule_session_title(
        container,
        session_store,
        thread_id,
        user_text=user_text,
        assistant_text=assistant_text,
    )
