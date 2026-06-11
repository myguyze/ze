from __future__ import annotations

from ze_core.interface.base import AppInterface
from ze_core.interface.types import Notification
from ze_core.logging import get_logger

log = get_logger(__name__)

_MAX_CONTENT_LEN = 4096


class ProactiveNotifier:
    """Delivers proactive notifications through the active AppInterface.

    This is a thin wrapper: callers build a Notification and call push().
    Errors are swallowed and logged — proactive pushes must never crash the caller.
    """

    def __init__(self, interface: AppInterface) -> None:
        self._interface = interface

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
