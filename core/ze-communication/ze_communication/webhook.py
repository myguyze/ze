from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ze_communication.types import InboundMessage


@dataclass
class WebhookPayload:
    source: str          # matches ChannelType value or WebhookHandler.source_key
    raw_body: bytes
    headers: dict[str, str]


class WebhookVerifier(ABC):
    """Implemented by each InboundChannel that supports push delivery."""

    @abstractmethod
    def verify(self, payload: WebhookPayload) -> bool:
        """Return True if the payload is authentic. Raise or return False otherwise."""
        ...

    @abstractmethod
    async def parse(self, payload: WebhookPayload) -> list[InboundMessage]:
        """Parse a verified payload into zero or more InboundMessages."""
        ...
