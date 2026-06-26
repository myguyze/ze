from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.channels.types import UserChannel
from ze_personal.channels.user_channel_store import UserChannelStore


def _make_pool(conn=None):
    if conn is None:
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _channel(channel_id: str = "gmail:alice@example.com", is_default: bool = False) -> UserChannel:
    return UserChannel(
        id=uuid4(),
        channel_id=channel_id,
        channel_type="email",
        handle="alice@example.com",
        display_name=None,
        is_default_outbound=is_default,
        poll_enabled=True,
        created_at=datetime.now(timezone.utc),
    )


def _row(channel: UserChannel) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, k: {
        "id": channel.id,
        "channel_id": channel.channel_id,
        "channel_type": channel.channel_type,
        "handle": channel.handle,
        "display_name": channel.display_name,
        "is_default_outbound": channel.is_default_outbound,
        "poll_enabled": channel.poll_enabled,
        "created_at": channel.created_at,
    }[k]
    return row


async def test_upsert_calls_execute():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    store = UserChannelStore(pool=_make_pool(conn))
    ch = _channel()
    await store.upsert(ch)
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "ON CONFLICT" in sql


async def test_list_all_returns_mapped_channels():
    ch = _channel()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_row(ch)])
    store = UserChannelStore(pool=_make_pool(conn))
    result = await store.list_all()
    assert len(result) == 1
    assert result[0].channel_id == ch.channel_id


async def test_get_default_outbound_returns_none_when_absent():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    store = UserChannelStore(pool=_make_pool(conn))
    result = await store.get_default_outbound("email")
    assert result is None


async def test_set_default_outbound_updates_in_transaction():
    ch = _channel(is_default=False)
    type_row = MagicMock()
    type_row.__getitem__ = lambda self, k: "email"

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=type_row)
    conn.execute = AsyncMock()

    # transaction context manager
    txn_cm = AsyncMock()
    txn_cm.__aenter__ = AsyncMock(return_value=None)
    txn_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=txn_cm)

    store = UserChannelStore(pool=_make_pool(conn))
    await store.set_default_outbound(ch.channel_id)

    assert conn.execute.call_count == 2
    first_sql = conn.execute.call_args_list[0][0][0]
    assert "FALSE" in first_sql


async def test_set_poll_enabled_executes_update():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    store = UserChannelStore(pool=_make_pool(conn))
    await store.set_poll_enabled("gmail:alice@example.com", False)
    conn.execute.assert_called_once()
    assert "poll_enabled" in conn.execute.call_args[0][0]
