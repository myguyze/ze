from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_agents.errors import ChannelNotFoundError
from ze_communication.channel import InboundChannel
from ze_communication.registry import ChannelRegistry
from ze_communication.types import ChannelType, Message, SentMessage
from ze_messenger.agents.messenger.tools import _resolve_send_channel


def _make_channel(channel_id: str = "gmail:ze@example.com") -> InboundChannel:
    from ze_google.gmail_channel import GmailChannel
    creds = MagicMock()
    creds.gmail.return_value = MagicMock()
    ch = GmailChannel(credentials=creds)
    ch._user_email = channel_id.replace("gmail:", "")
    return ch


def _make_registry(*channel_ids: str) -> ChannelRegistry:
    return ChannelRegistry(channels=[_make_channel(cid) for cid in channel_ids])


def _thread_map(mapping: dict | None = None) -> AsyncMock:
    m = AsyncMock()
    m.get = AsyncMock(side_effect=lambda tid: (mapping or {}).get(tid))
    m.set = AsyncMock()
    return m


def _user_channels(default: str | None = None) -> AsyncMock:
    store = AsyncMock()
    if default:
        uc = MagicMock()
        uc.channel_id = default
        store.get_default_outbound = AsyncMock(return_value=uc)
    else:
        store.get_default_outbound = AsyncMock(return_value=None)
    return store


# ── thread routing ────────────────────────────────────────────────────────────

async def test_resolves_thread_owner():
    registry = _make_registry("gmail:work@example.com", "gmail:personal@example.com")
    thread_map = _thread_map({"t1": "gmail:work@example.com"})
    user_channels = _user_channels()

    ch = await _resolve_send_channel(registry, thread_map, user_channels, thread_id="t1")
    assert ch.channel_id == "gmail:work@example.com"


async def test_falls_through_to_default_when_no_thread():
    registry = _make_registry("gmail:work@example.com", "gmail:personal@example.com")
    thread_map = _thread_map()
    user_channels = _user_channels(default="gmail:personal@example.com")

    ch = await _resolve_send_channel(registry, thread_map, user_channels, thread_id=None)
    assert ch.channel_id == "gmail:personal@example.com"


async def test_falls_through_to_any_channel_when_no_default():
    registry = _make_registry("gmail:ze@example.com")
    thread_map = _thread_map()
    user_channels = _user_channels()

    ch = await _resolve_send_channel(registry, thread_map, user_channels, thread_id=None)
    assert ch.channel_type.value == "email"


async def test_raises_when_no_email_channel():
    registry = ChannelRegistry(channels=[])
    thread_map = _thread_map()
    user_channels = _user_channels()

    with pytest.raises(ChannelNotFoundError):
        await _resolve_send_channel(registry, thread_map, user_channels, thread_id=None)
