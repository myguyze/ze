from __future__ import annotations

from typing import TYPE_CHECKING

from ze_agents.interface.base import AppInterface
from ze_agents.interface.types import Notification
from ze_logging import get_logger

if TYPE_CHECKING:
    from ze_proactive.notification_store import NotificationStore

log = get_logger(__name__)

_MAX_CONTENT_LEN = 4096


class ProactiveNotifier:
    """Delivers proactive notifications through the active AppInterface."""

    def __init__(
        self,
        interface: AppInterface,
        notification_store: "NotificationStore | None" = None,
    ) -> None:
        self._interface = interface
        self._store = notification_store

    async def notify(
        self,
        event_type: str,
        title: str,
        body: str,
        *,
        source: str,
        target_type: str | None = None,
        target_id: str | None = None,
        hours: float | None = None,
        urgency: str = "normal",
    ) -> None:
        """Persist and deliver a structured notification (notification center).

        When `hours` is given, skips both persistence and delivery if a
        notification with the same `event_type` + `target_type`/`target_id`
        was already created within the window (research R3).
        """
        if self._store is None:
            log.warning("proactive_notify_no_store", event_type=event_type)
            return

        if hours is not None:
            duplicate = await self._store.exists_recent(
                event_type=event_type,
                target_type=target_type,
                target_id=target_id,
                hours=hours,
            )
            if duplicate:
                log.debug(
                    "proactive_notify_deduped",
                    event_type=event_type,
                    target_id=target_id,
                )
                return

        row = await self._store.create(
            event_type=event_type,
            source=source,
            title=title,
            body=body,
            target_type=target_type,
            target_id=target_id,
        )

        notification = Notification(
            content=body,
            urgency=urgency,
            id=row.id,
            event_type=row.event_type,
            source=row.source,
            title=row.title,
            target_type=row.target_type,
            target_id=row.target_id,
            created_at=row.created_at,
        )
        try:
            await self._interface.push(notification)
        except Exception as exc:
            log.warning("proactive_push_failed", error=str(exc))

    async def push(
        self,
        content: str,
        *,
        format: str = "text",
        urgency: str = "normal",
    ) -> None:
        """Send a plain notification to the user."""
        for chunk in _split(content):
            notification = Notification(content=chunk, format=format, urgency=urgency)
            try:
                await self._interface.push(notification)
            except Exception as exc:
                log.warning("proactive_push_failed", error=str(exc))

    async def push_notification(self, notification: Notification) -> None:
        """Send a pre-built Notification, splitting oversized content automatically."""
        if len(notification.content) <= _MAX_CONTENT_LEN:
            try:
                await self._interface.push(notification)
            except Exception as exc:
                log.warning("proactive_push_failed", error=str(exc))
            return

        chunks = _split(notification.content)
        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            n = Notification(
                content=chunk,
                format=notification.format,
                urgency=notification.urgency,
                actions=notification.actions if is_last else [],
                metadata=notification.metadata,
            )
            try:
                await self._interface.push(n)
            except Exception as exc:
                log.warning("proactive_push_failed", error=str(exc))


def _split(text: str, limit: int = _MAX_CONTENT_LEN) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    return chunks
