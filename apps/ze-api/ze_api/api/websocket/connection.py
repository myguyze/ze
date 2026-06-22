from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket

from ze_api.api.websocket.serializers import message_to_dict
from ze_logging import get_logger

log = get_logger(__name__)


class ConnectionManager:
    """Holds the single active WebSocket connection."""

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._lock = asyncio.Lock()
        self._busy = False
        self._thread_id: str | None = None

    @property
    def connected(self) -> bool:
        return self._ws is not None

    @property
    def thread_id(self) -> str | None:
        return self._thread_id

    async def connect(
        self,
        ws: WebSocket,
        message_store: Any,
        confirmation_store: Any | None = None,
        thread_id: str | None = None,
    ) -> None:
        async with self._lock:
            if self._ws is not None:
                try:
                    await self._ws.close(code=4000)
                except Exception:
                    pass
            self._ws = ws
            self._busy = False
            self._thread_id = thread_id

        unread = await message_store.list_unread(thread_id)
        async with self._lock:
            for msg in unread:
                try:
                    await self._ws.send_json({"type": "message", "message": message_to_dict(msg)})
                except Exception:
                    self._ws = None
                    break

        if confirmation_store is not None:
            try:
                pending = await confirmation_store.get_any_pending()
                if pending is not None:
                    async with self._lock:
                        if self._ws is not None:
                            try:
                                await self._ws.send_json({
                                    "type": "confirm_request",
                                    "id": pending["request_id"],
                                    "prompt": pending["prompt"],
                                    "actions": pending["actions"],
                                })
                            except Exception as exc:
                                log.warning("ws_confirmation_replay_failed", error=str(exc))
            except Exception as exc:
                log.warning("ws_confirmation_replay_error", error=str(exc))

    async def disconnect(self) -> None:
        async with self._lock:
            self._ws = None
            self._thread_id = None

    async def push(self, message: Any) -> None:
        """Send a message frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json({"type": "message", "message": message_to_dict(message)})
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
        """Attempt to claim the invocation slot. Returns True on success.

        Safe without the lock: asyncio runs one coroutine at a time and there
        is no await between the check and the set, so no other coroutine can
        interleave here. Moving this under the lock would require making it
        async, changing all call sites.
        """
        if self._busy:
            return False
        self._busy = True
        return True

    def clear_busy(self) -> None:
        self._busy = False
