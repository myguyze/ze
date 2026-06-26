from datetime import datetime

import pytest

from ze_communication.channel import Channel, InboundChannel
from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelType, InboundMessage, Message, SentMessage, Thread
from ze_agents.errors import ChannelError, ChannelNotFoundError


class _StubChannel(Channel):
    def __init__(self, ctype: ChannelType = ChannelType.EMAIL) -> None:
        self._type = ctype

    @property
    def channel_type(self) -> ChannelType:
        return self._type

    async def send(self, message: Message) -> SentMessage:
        raise NotImplementedError

    async def get_thread(self, thread_id: str) -> Thread:
        raise NotImplementedError


class _StubInboundChannel(_StubChannel, InboundChannel):
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]:
        return []


def _registry(*types: ChannelType) -> ChannelRegistry:
    return ChannelRegistry([_StubChannel(t) for t in types])


# ── get() ─────────────────────────────────────────────────────────────────────

def test_get_registered_channel():
    reg = _registry(ChannelType.EMAIL)
    assert reg.get(ChannelType.EMAIL).channel_type == ChannelType.EMAIL


def test_get_missing_raises_channel_not_found():
    reg = _registry(ChannelType.EMAIL)
    with pytest.raises(ChannelNotFoundError):
        reg.get(ChannelType.LINKEDIN)


def test_channel_not_found_is_channel_error():
    with pytest.raises(ChannelError):
        _registry().get(ChannelType.EMAIL)


def test_last_registered_wins_for_same_type():
    ch1 = _StubChannel(ChannelType.EMAIL)
    ch2 = _StubChannel(ChannelType.EMAIL)
    reg = ChannelRegistry([ch1, ch2])
    assert reg.get(ChannelType.EMAIL) is ch2


# ── available() ───────────────────────────────────────────────────────────────

def test_available_returns_registered_types():
    reg = _registry(ChannelType.EMAIL, ChannelType.WHATSAPP)
    assert set(reg.available()) == {ChannelType.EMAIL, ChannelType.WHATSAPP}


def test_available_empty():
    assert _registry().available() == []


# ── get_inbound() ─────────────────────────────────────────────────────────────

def test_get_inbound_returns_inbound_channel():
    inbound = _StubInboundChannel(ChannelType.EMAIL)
    reg = ChannelRegistry([inbound])
    assert reg.get_inbound(ChannelType.EMAIL) is inbound


def test_get_inbound_returns_none_for_outbound_only():
    reg = _registry(ChannelType.EMAIL)
    assert reg.get_inbound(ChannelType.EMAIL) is None


def test_get_inbound_returns_none_for_missing():
    reg = _registry()
    assert reg.get_inbound(ChannelType.EMAIL) is None


# ── inbound_channels() ────────────────────────────────────────────────────────

def test_inbound_channels_filters_correctly():
    inbound = _StubInboundChannel(ChannelType.EMAIL)
    outbound = _StubChannel(ChannelType.LINKEDIN)
    reg = ChannelRegistry([inbound, outbound])
    result = reg.inbound_channels()
    assert result == [inbound]


def test_inbound_channels_empty_when_none():
    reg = _registry(ChannelType.EMAIL)
    assert reg.inbound_channels() == []
