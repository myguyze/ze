from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ze_communication.webhook import WebhookPayload


@runtime_checkable
class WebhookHandler(Protocol):
    """Implemented by plugins that receive non-channel webhook events."""

    source_key: str

    def verify(self, payload: WebhookPayload) -> bool:
        """Return True if the payload is authentic."""
        ...

    async def handle(self, payload: WebhookPayload) -> None:
        """Process a verified payload. Fire-and-forget; errors are logged and swallowed."""
        ...
