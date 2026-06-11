from typing import Protocol

from ze_notifications.types import Notification


class Notifier(Protocol):
    async def push(self, notification: Notification) -> None:
        """
        Push a notification. Implementations must:
        - Never raise on delivery failure (log and return).
        - Be async.
        """
        ...
