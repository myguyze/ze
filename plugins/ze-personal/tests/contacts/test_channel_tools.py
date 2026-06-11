from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ze_core.channels.types import ChannelHandle, ChannelType
from ze_personal.contacts.tools import get_contact_channels, set_contact_channel


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_store(handles: list[ChannelHandle] | None = None):
    store = AsyncMock()
    store.get_handles = AsyncMock(return_value=handles or [])
    store.upsert = AsyncMock()
    return store


# ── get_contact_channels ──────────────────────────────────────────────────────

async def test_get_contact_channels_returns_handles():
    contact_id = str(uuid4())
    handles = [
        ChannelHandle(ChannelType.EMAIL, "alice@example.com", preferred=True, verified=True),
        ChannelHandle(ChannelType.LINKEDIN, "https://linkedin.com/in/alice"),
    ]
    store = make_store(handles)
    tc = await get_contact_channels(
        contact_id=contact_id,
        contact_channel_store=store,
    )
    assert tc.success is True
    assert len(tc.result) == 2
    assert tc.result[0]["channel_type"] == "email"
    assert tc.result[0]["preferred"] is True
    assert tc.result[1]["channel_type"] == "linkedin"


async def test_get_contact_channels_returns_empty_list_when_none():
    tc = await get_contact_channels(
        contact_id=str(uuid4()),
        contact_channel_store=make_store([]),
    )
    assert tc.success is True
    assert tc.result == []


async def test_get_contact_channels_fails_gracefully_on_error():
    store = make_store()
    store.get_handles = AsyncMock(side_effect=Exception("db error"))
    tc = await get_contact_channels(
        contact_id=str(uuid4()),
        contact_channel_store=store,
    )
    assert tc.success is False
    assert tc.result == []


async def test_get_contact_channels_fails_on_invalid_uuid():
    tc = await get_contact_channels(
        contact_id="not-a-uuid",
        contact_channel_store=make_store(),
    )
    assert tc.success is False


# ── set_contact_channel ───────────────────────────────────────────────────────

async def test_set_contact_channel_upserts_handle():
    contact_id = str(uuid4())
    store = make_store()
    tc = await set_contact_channel(
        contact_id=contact_id,
        channel_type="email",
        handle="bob@example.com",
        contact_channel_store=store,
        preferred=True,
    )
    assert tc.success is True
    store.upsert.assert_awaited_once()
    handle_arg = store.upsert.call_args.args[1]
    assert handle_arg.channel_type == ChannelType.EMAIL
    assert handle_arg.handle == "bob@example.com"
    assert handle_arg.preferred is True


async def test_set_contact_channel_defaults_preferred_false():
    store = make_store()
    await set_contact_channel(
        contact_id=str(uuid4()),
        channel_type="linkedin",
        handle="https://linkedin.com/in/bob",
        contact_channel_store=store,
    )
    handle_arg = store.upsert.call_args.args[1]
    assert handle_arg.preferred is False


async def test_set_contact_channel_fails_on_invalid_channel_type():
    tc = await set_contact_channel(
        contact_id=str(uuid4()),
        channel_type="fax",
        handle="555-1234",
        contact_channel_store=make_store(),
    )
    assert tc.success is False


async def test_set_contact_channel_fails_gracefully_on_store_error():
    store = make_store()
    store.upsert = AsyncMock(side_effect=Exception("db error"))
    tc = await set_contact_channel(
        contact_id=str(uuid4()),
        channel_type="email",
        handle="x@x.com",
        contact_channel_store=store,
    )
    assert tc.success is False
    assert tc.result is None
