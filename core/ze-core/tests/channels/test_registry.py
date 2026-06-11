from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from ze_core.channels.base import Channel
from ze_core.channels.registry import ChannelRegistry
from ze_core.channels.types import ChannelType, Message, SentMessage, Thread, ThreadMessage
from ze_core.errors import ChannelNotFoundError


class _StubChannel(Channel):
    def __init__(self, ctype: ChannelType) -> None:
        self._type = ctype

    @property
    def channel_type(self) -> ChannelType:
        return self._type

    async def send(self, message: Message) -> SentMessage:
        raise NotImplementedError

    async def get_thread(self, thread_id: str) -> Thread:
        raise NotImplementedError

    async def poll_replies(self, thread_ids: list[str], since: datetime) -> list[ThreadMessage]:
        return []


def _registry(*types: ChannelType) -> ChannelRegistry:
    return ChannelRegistry([_StubChannel(t) for t in types])


def test_get_registered_channel():
    reg = _registry(ChannelType.EMAIL)
    ch = reg.get(ChannelType.EMAIL)
    assert ch.channel_type == ChannelType.EMAIL


def test_get_missing_channel_raises():
    reg = _registry(ChannelType.EMAIL)
    with pytest.raises(ChannelNotFoundError):
        reg.get(ChannelType.LINKEDIN)


def test_available_returns_registered_types():
    reg = _registry(ChannelType.EMAIL, ChannelType.WHATSAPP)
    assert set(reg.available()) == {ChannelType.EMAIL, ChannelType.WHATSAPP}


def test_available_empty():
    reg = ChannelRegistry([])
    assert reg.available() == []


def test_last_registered_wins_for_same_type():
    ch1 = _StubChannel(ChannelType.EMAIL)
    ch2 = _StubChannel(ChannelType.EMAIL)
    reg = ChannelRegistry([ch1, ch2])
    assert reg.get(ChannelType.EMAIL) is ch2
