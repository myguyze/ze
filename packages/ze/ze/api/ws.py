from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from ze_core.messages.types import Message
from ze_core.interface.types import RawInput
from ze.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["websocket"])


class ConnectionManager:
    """Holds the single active WebSocket connection."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._lock = asyncio.Lock()
        self._busy = False

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def connect(self, ws: WebSocket, message_store: Any) -> None:
        async with self._lock:
            if self._ws is not None:
                try:
                    await self._ws.close(code=4000)
                except Exception:
                    pass
            self._ws = ws
            self._busy = False

        unread = await message_store.list_unread()
        async with self._lock:
            for msg in unread:
                try:
                    await self._ws.send_json({"type": "message", "message": _message_to_dict(msg)})
                except Exception:
                    self._ws = None
                    break

    async def disconnect(self) -> None:
        async with self._lock:
            self._ws = None

    async def push(self, message: Message) -> None:
        """Send a message frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json({"type": "message", "message": _message_to_dict(message)})
            except Exception as exc:
                log.warning("ws_push_failed", error=str(exc))
                self._ws = None

    async def send_frame(self, frame: dict) -> None:
        """Send an arbitrary JSON frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json(frame)
            except Exception as exc:
                log.warning("ws_send_frame_failed", error=str(exc))
                self._ws = None

    def try_set_busy(self) -> bool:
        """Attempt to claim the invocation slot. Returns True on success."""
        if self._busy:
            return False
        self._busy = True
        return True

    def clear_busy(self) -> None:
        self._busy = False


@router.websocket("/ws")
async def websocket_endpoint(request: Request, ws: WebSocket, token: str | None = None) -> None:
    settings = request.app.state.settings
    api_key: str = settings.ze_api_key

    auth_header = ws.headers.get("Authorization", "")
    bearer = auth_header.removeprefix("Bearer ").strip() if auth_header.startswith("Bearer ") else ""

    if bearer != api_key and token != api_key:
        await ws.close(code=4001)
        return

    await ws.accept()

    conn_mgr: ConnectionManager = request.app.state.connection_manager
    msg_store = request.app.state.message_store
    container = request.app.state.container

    await conn_mgr.connect(ws, msg_store)
    log.info("ws_connected")

    pending_config: dict | None = None

    try:
        while True:
            try:
                data = await ws.receive_json()
            except WebSocketDisconnect:
                break

            frame_type = data.get("type")

            if frame_type == "ping":
                await ws.send_json({"type": "pong"})

            elif frame_type == "ack":
                ids = [UUID(i) for i in data.get("ids", [])]
                await msg_store.mark_read(ids)

            elif frame_type == "command":
                pending_config = await _handle_command(
                    ws, data, container, conn_mgr, pending_config
                )

            elif frame_type == "message":
                if not conn_mgr.try_set_busy():
                    await ws.send_json({"type": "error", "detail": "busy"})
                    continue

                try:
                    pending_config = await _handle_message(
                        ws, data, container, msg_store, conn_mgr, pending_config
                    )
                finally:
                    conn_mgr.clear_busy()

    except Exception as exc:
        log.exception("ws_handler_error", error=str(exc))
    finally:
        await conn_mgr.disconnect()
        log.info("ws_disconnected")


async def _handle_message(
    ws: WebSocket,
    data: dict,
    container: Any,
    msg_store: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
) -> dict | None:
    text: str = data.get("text", "")
    thread_id: str | None = data.get("thread_id") or None
    context: dict | None = data.get("context") or None

    if not text:
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

    await conn_mgr.send_frame({"type": "typing"})

    config_extra: dict = {}
    if context:
        config_extra["screen_context"] = context
    if thread_id:
        config_extra["thread_id"] = thread_id

    try:
        outcome = await container.invoke_raw_turn(
            thread_id or f"ws-{uuid4()}",
            RawInput(text=text),
            config_extra=config_extra,
        )
    except Exception as exc:
        log.exception("ws_invoke_error", error=str(exc))
        await conn_mgr.send_frame({"type": "error", "detail": "Something went wrong."})
        return None

    if outcome.interrupted:
        request_id = str(uuid4())
        await conn_mgr.send_frame({
            "type": "confirm_request",
            "id": request_id,
            "prompt": outcome.draft or "",
            "actions": [
                {"label": "Approve", "payload": "yes"},
                {"label": "Cancel", "payload": "no"},
            ],
        })
        return outcome.config

    if outcome.response:
        components = outcome.final_state.get("components", [])
        await container.interface.send_with_thread(
            outcome.response,
            thread_id=_extract_thread_id(outcome.config),
            components=components or None,
        )

    return None


async def _handle_command(
    ws: WebSocket,
    data: dict,
    container: Any,
    conn_mgr: ConnectionManager,
    pending_config: dict | None,
) -> dict | None:
    name = data.get("name", "")

    if name == "cancel":
        if pending_config is not None:
            await conn_mgr.send_frame({"type": "confirm_cancel", "id": ""})
            return None
        await container.abort_invocation(pending_config.get("configurable", {}).get("thread_id", ""))
        return None

    if name == "costs":
        from ze.api.routes.costs import _build_cost_summary
        try:
            summary = await _build_cost_summary(container)
            await conn_mgr.send_frame({"type": "message", "message": {"role": "assistant", "text": summary, "components": []}})
        except Exception as exc:
            log.warning("ws_costs_command_failed", error=str(exc))
        return pending_config

    log.warning("ws_unknown_command", name=name)
    return pending_config


def _extract_thread_id(config: dict) -> str | None:
    return config.get("configurable", {}).get("thread_id")


def _message_to_dict(msg: Message) -> dict:
    return {
        "id": str(msg.id),
        "role": msg.role,
        "text": msg.text,
        "components": msg.components,
        "read": msg.read,
        "thread_id": msg.thread_id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }
