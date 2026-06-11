from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, ClassVar, Literal
from uuid import uuid4

from ze_core.interface.types import ConfirmationRequest, Notification, OutboundMessage
from ze_core.messages.types import Message
from ze_api.logging import get_logger

if TYPE_CHECKING:
    from ze_notifications.notifier import Notifier as PushNotifier
    from ze_core.messages.store import MessageStore
    from ze_api.api.ws import ConnectionManager

log = get_logger(__name__)

_NTFY_PRIORITY_MAP = {"normal": 3, "high": 5}


class NativeAppInterface:
    """AppInterface for the native Flutter app — WebSocket + ntfy delivery."""

    confirmation_style: ClassVar[Literal["inline", "async"]] = "async"

    def __init__(
        self,
        message_store: MessageStore,
        connection_manager: ConnectionManager,
        notifier: PushNotifier | None,
    ) -> None:
        self._store = message_store
        self._conn = connection_manager
        self._notifier = notifier

    async def send(self, message: OutboundMessage) -> None:
        await self._send_message(message.content)

    async def push(self, notification: Notification) -> None:
        await self._send_message(
            notification.content,
            ntfy_priority=_NTFY_PRIORITY_MAP.get(notification.urgency, 3),
        )

    async def _send_message(
        self,
        text: str,
        thread_id: str | None = None,
        components: list[dict] | None = None,
        ntfy_priority: int = 3,
    ) -> None:
        msg = Message(
            id=uuid4(),
            role="assistant",
            text=text,
            components=components or [],
            read=False,
            created_at=datetime.now(timezone.utc),
            thread_id=thread_id,
        )
        try:
            await self._store.save(msg)
        except Exception as exc:
            log.warning("native_interface_save_failed", error=str(exc))

        await self._conn.push(msg)

        if self._notifier is not None:
            from ze_notifications.types import Notification as PushNotification
            try:
                await self._notifier.push(
                    PushNotification(
                        title="Ze",
                        body=text[:200],
                        priority=ntfy_priority,
                    )
                )
            except Exception as exc:
                log.warning("native_interface_ntfy_failed", error=str(exc))

    async def send_with_thread(
        self,
        text: str,
        thread_id: str | None,
        components: list[dict] | None = None,
    ) -> None:
        """Called by the WS handler after graph invocation to attach the thread_id."""
        await self._send_message(text, thread_id=thread_id, components=components)
