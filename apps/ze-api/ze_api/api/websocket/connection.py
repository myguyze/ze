from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import WebSocket

from ze_api.api.websocket.serializers import message_to_dict
from ze_logging import get_logger

log = get_logger(__name__)


@dataclass
class ThreadSlot:
    busy: bool = False
    pending_gate_redirect: UUID | None = None


class ConnectionManager:
    """Multiplexed single-WebSocket connection manager.

    One WebSocket is kept alive for the whole browser session.  Per-thread state
    (busy flag, pending gate redirect) lives in ThreadSlot objects keyed by
    thread_id.  Every outbound frame is tagged with the originating thread_id so
    the client can route delivery without reconnecting.
    """

    def __init__(self) -> None:
        self._ws: WebSocket | None = None
        self._lock = asyncio.Lock()
        self._slots: dict[str, ThreadSlot] = {}

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def _slot(self, thread_id: str) -> ThreadSlot:
        if thread_id not in self._slots:
            self._slots[thread_id] = ThreadSlot()
        return self._slots[thread_id]

    async def connect(
        self,
        ws: WebSocket,
        message_store: Any,
        confirmation_store: Any | None = None,
    ) -> None:
        async with self._lock:
            if self._ws is not None:
                try:
                    await self._ws.close(code=4000)
                except Exception:
                    pass
            self._ws = ws
            # Previous session is gone; reset all busy flags so new messages
            # can be processed even if a prior run was interrupted mid-flight.
            for slot in self._slots.values():
                slot.busy = False

        # Replay all unread messages across all threads, tagged with their thread_id.
        unread = await message_store.list_unread(None)
        async with self._lock:
            for msg in unread:
                try:
                    await self._ws.send_json(
                        {"type": "message", "message": message_to_dict(msg)}
                    )
                except Exception:
                    self._ws = None
                    break

        # Replay all pending confirmations, each tagged with their thread_id.
        if confirmation_store is not None:
            try:
                pending_list = await confirmation_store.get_all_pending()
                for pending in pending_list:
                    async with self._lock:
                        if self._ws is not None:
                            try:
                                await self._ws.send_json(
                                    {
                                        "type": "confirm_request",
                                        "thread_id": pending["thread_id"],
                                        "id": pending["request_id"],
                                        "prompt": pending["prompt"],
                                        "actions": pending["actions"],
                                    }
                                )
                            except Exception as exc:
                                log.warning(
                                    "ws_confirmation_replay_failed", error=str(exc)
                                )
            except Exception as exc:
                log.warning("ws_confirmation_replay_error", error=str(exc))

    async def disconnect(self) -> None:
        async with self._lock:
            self._ws = None
            for slot in self._slots.values():
                slot.pending_gate_redirect = None

    def set_pending_gate_redirect(self, gate_id: UUID, thread_id: str) -> None:
        self._slot(thread_id).pending_gate_redirect = gate_id

    def take_pending_gate_redirect(self, thread_id: str) -> UUID | None:
        slot = self._slot(thread_id)
        gate_id = slot.pending_gate_redirect
        slot.pending_gate_redirect = None
        return gate_id

    async def push(self, message: Any, thread_id: str | None = None) -> None:
        """Send a message frame; silently no-ops if disconnected."""
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json(
                    {"type": "message", "message": message_to_dict(message)}
                )
            except Exception as exc:
                log.warning("ws_push_failed", error=str(exc))
                self._ws = None

    async def send_frame(self, frame: dict, thread_id: str | None = None) -> None:
        """Send an arbitrary JSON frame, injecting thread_id when provided."""
        if thread_id is not None:
            frame = {**frame, "thread_id": thread_id}
        async with self._lock:
            if self._ws is None:
                return
            try:
                await self._ws.send_json(frame)
            except Exception as exc:
                log.warning("ws_send_frame_failed", error=str(exc))
                self._ws = None

    def try_set_busy(self, thread_id: str) -> bool:
        """Attempt to claim the invocation slot for thread_id. Returns True on success.

        Safe without the lock: asyncio runs one coroutine at a time and there
        is no await between the check and the set, so no other coroutine can
        interleave here.
        """
        slot = self._slot(thread_id)
        if slot.busy:
            return False
        slot.busy = True
        return True

    def clear_busy(self, thread_id: str) -> None:
        self._slot(thread_id).busy = False
