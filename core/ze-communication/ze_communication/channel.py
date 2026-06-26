from abc import ABC, abstractmethod
from datetime import datetime

from ze_communication.types import (
    ChannelType,
    InboundMessage,
    Message,
    SentMessage,
    Thread,
)


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
    on a schedule. If True, messages arrive via the webhook path (Phase 84).
    """

    @property
    def supports_push(self) -> bool:
        return False

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
