from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ze_agents.channels.types import ChannelType, Message, SentMessage, Thread, ThreadMessage


class Channel(ABC):
    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    async def send(self, message: Message) -> SentMessage: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Thread: ...

    @abstractmethod
    async def poll_replies(
        self,
        thread_ids: list[str],
        since: datetime,
    ) -> list[ThreadMessage]: ...
