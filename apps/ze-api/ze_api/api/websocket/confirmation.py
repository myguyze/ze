from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import WebSocket

from ze_agents.tasks import fire_and_forget
from ze_api.api.websocket.connection import ConnectionManager
from ze_api.api.websocket.serializers import ephemeral_assistant_message, extract_thread_id
from ze_api.logging import get_logger

log = get_logger(__name__)


async def handle_confirm(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
    *,
    confirmation_store: Any | None = None,
    session_store: Any | None = None,
) -> dict | None:
    choice = data.get("choice", "")
    request_id = data.get("id", "")

    if pending_config is None:
        await conn_mgr.send_frame({"type": "error", "detail": "No pending confirmation."})
        return None

    thread_id = extract_thread_id(pending_config) or ""
    if confirmation_store is not None and thread_id:
        await confirmation_store.clear(thread_id)

    if choice == "approve":
        if not conn_mgr.try_set_busy():
            await conn_mgr.send_frame({"type": "error", "detail": "busy"})
            return pending_config
        try:
            await conn_mgr.send_frame({"type": "typing"})
            outcome = await container.resume_turn(pending_config)
        except Exception as exc:
            log.exception("ws_resume_error", error=str(exc))
            await conn_mgr.send_frame({"type": "error", "detail": "Resume failed."})
            return None
        finally:
            conn_mgr.clear_busy()

        if outcome.response:
            if session_store is not None and thread_id:
                preview = outcome.response[:120].strip()
                try:
                    await session_store.upsert(thread_id, preview=preview)
                except Exception as exc:
                    log.warning("ws_session_preview_update_failed", error=str(exc))

            components = outcome.final_state.get("components", [])
            await container.interface.send_with_thread(
                outcome.response,
                thread_id=thread_id,
                components=components or None,
            )
        return None

    try:
        await container.abort_pending_checkpoint(pending_config)
    except Exception as exc:
        log.warning("ws_deny_abort_failed", error=str(exc))
    await conn_mgr.send_frame({"type": "confirm_cancel", "id": request_id})
    return None


async def push_confirmation_ntfy(notifier: Any, prompt: str) -> None:
    try:
        text = f"Ze needs your approval:\n{prompt}" if prompt else "Ze needs your approval."
        await notifier.push(text, urgency="high")
    except Exception as exc:
        log.warning("ws_confirmation_ntfy_failed", error=str(exc))


async def confirmation_timeout(
    confirmation_store: Any,
    conn_mgr: ConnectionManager,
    notifier: Any | None,
    thread_id: str,
    timeout_seconds: int,
    container: Any | None = None,
    graph_config: dict | None = None,
) -> None:
    await asyncio.sleep(timeout_seconds)
    cleared = await confirmation_store.clear(thread_id)
    if not cleared:
        return

    log.info("confirmation_timeout_elapsed", thread_id=thread_id)

    if container is not None and graph_config is not None:
        try:
            await container.abort_pending_checkpoint(graph_config)
        except Exception as exc:
            log.warning("ws_timeout_checkpoint_abort_failed", error=str(exc))

    timeout_msg = (
        "I waited for your approval but the window elapsed — "
        "let me know if you'd like me to try again."
    )
    await conn_mgr.send_frame({
        "type": "message",
        "message": ephemeral_assistant_message(timeout_msg),
    })
    if notifier is not None:
        try:
            await notifier.push(timeout_msg, urgency="low")
        except Exception as exc:
            log.warning("ws_timeout_ntfy_failed", error=str(exc))


async def send_confirmation_request(
    conn_mgr: ConnectionManager,
    container: Any,
    outcome: Any,
    thread_id: str,
    *,
    confirmation_store: Any | None = None,
) -> dict:
    """Persist, notify, and frame a confirmation request; returns graph config."""
    request_id = str(uuid4())
    effective_thread_id = extract_thread_id(outcome.config) or thread_id or ""
    confirm_timeout = getattr(container.settings, "confirm_timeout_seconds", 900)

    frame = {
        "type": "confirm_request",
        "id": request_id,
        "prompt": outcome.draft or "",
        "actions": [
            {"label": "Approve", "value": "approve", "style": "primary"},
            {"label": "Cancel", "value": "deny", "style": "secondary"},
        ],
    }

    if confirmation_store is not None and effective_thread_id:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=confirm_timeout)
        await confirmation_store.save(
            thread_id=effective_thread_id,
            request_id=request_id,
            prompt=outcome.draft or "",
            actions=frame["actions"],
            expires_at=expires_at,
        )

    await conn_mgr.send_frame(frame)

    notifier = getattr(container, "notifier", None)
    if notifier is not None:
        fire_and_forget(
            push_confirmation_ntfy(notifier, outcome.draft or ""),
            label="push_confirmation_ntfy",
        )

    if confirmation_store is not None and effective_thread_id:
        asyncio.create_task(confirmation_timeout(
            confirmation_store,
            conn_mgr,
            notifier,
            effective_thread_id,
            confirm_timeout,
            container=container,
            graph_config=outcome.config,
        ))

    return outcome.config
