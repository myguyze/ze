from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING

from ze_communication.types import (
    ChannelType,
    InboundMessage,
    Message,
    SentMessage,
    Thread,
)

if TYPE_CHECKING:
    from ze_communication.webhook import WebhookVerifier


class Channel(ABC):
    """Outbound channel contract. All channels must implement this."""

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    async def send(self, message: Message) -> SentMessage: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Thread: ...


class InboundChannel(Channel):
    """Channel that can also receive messages, via polling or push.

    Polling callers check supports_push first. If False, call poll_new_messages
    on a schedule. If True, messages arrive via the webhook path (Phase 86).
    """

    @property
    def channel_id(self) -> str:
        """Unique identifier for this channel instance (e.g. "gmail:joao@gmail.com").

        Default returns channel_type.value — correct for single-account deployments.
        Override in multi-account scenarios.
        """
        return self.channel_type.value

    @property
    def supports_push(self) -> bool:
        return False

    def webhook_verifier(self) -> "WebhookVerifier | None":
        """Return a verifier when supports_push is True, else None."""
        return None

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
