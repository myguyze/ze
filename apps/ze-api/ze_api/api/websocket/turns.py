from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from ze_agents.interface.types import RawInput
from ze_agents.progress.reporter import ProgressReporter
from ze_api.api.websocket.confirmation import send_confirmation_request
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.serializers import extract_thread_id
from ze_api.logging import get_logger
from ze_core.messages.types import Message

log = get_logger(__name__)


async def handle_message(
    ws: WebSocket,
    data: dict,
    container: Any,
    msg_store: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
    *,
    confirmation_store: Any | None = None,
    session_store: Any | None = None,
) -> dict | None:
    text: str = data.get("text", "")
    thread_id: str | None = data.get("thread_id") or None
    context: dict | None = data.get("context") or None

    if not text:
        return pending_config

    if not thread_id:
        await conn_mgr.send_frame({"type": "error", "detail": "thread_id required"})
        return pending_config

    user_msg = Message(
        id=uuid4(),
        role="user",
        text=text,
        components=[],
        read=True,
        created_at=datetime.now(timezone.utc),
        thread_id=thread_id,
    )
    try:
        await msg_store.save(user_msg)
    except Exception as exc:
        log.warning("ws_save_user_msg_failed", error=str(exc))

    if session_store is not None and thread_id:
        title = text[:60].strip() if text else None
        try:
            await session_store.upsert(thread_id, title=title)
        except Exception as exc:
            log.warning("ws_session_upsert_failed", error=str(exc))

    await conn_mgr.send_frame({"type": "typing"})

    config_extra: dict = {}
    if context:
        config_extra["screen_context"] = context

    if getattr(container, "translations", None) is not None:
        async def _progress_sink(text: str) -> None:
            await conn_mgr.send_frame({"type": "typing", "text": text})

        config_extra["reporter"] = ProgressReporter(
            translations=container.translations,
            sink=_progress_sink,
        )

    try:
        outcome = await container.invoke_raw_turn(
            thread_id,
            RawInput(text=text),
            config_extra=config_extra,
        )
    except Exception as exc:
        log.exception("ws_invoke_error", error=str(exc))
        await conn_mgr.send_frame({"type": "error", "detail": "Something went wrong."})
        return None

    if outcome.interrupted:
        return await send_confirmation_request(
            conn_mgr,
            container,
            outcome,
            thread_id,
            confirmation_store=confirmation_store,
        )

    if outcome.response:
        effective_thread_id = extract_thread_id(outcome.config) or thread_id or ""
        if confirmation_store is not None and effective_thread_id:
            await confirmation_store.clear(effective_thread_id)

        if session_store is not None and effective_thread_id:
            preview = outcome.response[:120].strip() if outcome.response else None
            try:
                await session_store.upsert(effective_thread_id, preview=preview)
            except Exception as exc:
                log.warning("ws_session_preview_update_failed", error=str(exc))

        components = outcome.final_state.get("components", [])
        await container.interface.send_with_thread(
            outcome.response,
            thread_id=extract_thread_id(outcome.config),
            components=components or None,
        )

    return None
