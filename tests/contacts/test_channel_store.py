from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.channels.types import ChannelHandle, ChannelType
from ze.contacts.channel_store import ContactChannelStore, _handle_from_row


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    # transaction() context manager
    tx_cm = AsyncMock()
    tx_cm.__aenter__ = AsyncMock(return_value=None)
    tx_cm.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx_cm)
    return conn


def make_pool(conn=None):
    conn = conn or make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_store(conn=None):
    return ContactChannelStore(pool=make_pool(conn))


def make_row(**overrides):
    defaults = {
        "id": uuid4(),
        "contact_id": uuid4(),
        "channel_type": "email",
        "handle": "alice@example.com",
        "preferred": False,
        "verified": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return defaults


# ── _handle_from_row ──────────────────────────────────────────────────────────

def test_handle_from_row_maps_fields():
    row = make_row(channel_type="email", handle="a@b.com", preferred=True, verified=True)
    h = _handle_from_row(row)
    assert h.channel_type == ChannelType.EMAIL
    assert h.handle == "a@b.com"
    assert h.preferred is True
    assert h.verified is True


# ── get_handles ───────────────────────────────────────────────────────────────

async def test_get_handles_returns_empty_when_none():
    store = make_store()
    result = await store.get_handles(uuid4())
    assert result == []


async def test_get_handles_returns_all_handles():
    rows = [
        make_row(channel_type="email", handle="a@b.com", preferred=True),
        make_row(channel_type="linkedin", handle="https://linkedin.com/in/alice"),
    ]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)
    store = make_store(conn)
    handles = await store.get_handles(uuid4())
    assert len(handles) == 2
    types = {h.channel_type for h in handles}
    assert types == {ChannelType.EMAIL, ChannelType.LINKEDIN}


# ── get_preferred ─────────────────────────────────────────────────────────────

async def test_get_preferred_returns_none_when_no_preferred():
    store = make_store()
    result = await store.get_preferred(uuid4())
    assert result is None


async def test_get_preferred_returns_preferred_handle():
    row = make_row(channel_type="email", handle="a@b.com", preferred=True)
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=row)
    store = make_store(conn)
    handle = await store.get_preferred(uuid4())
    assert handle is not None
    assert handle.preferred is True
    assert handle.channel_type == ChannelType.EMAIL


# ── upsert ────────────────────────────────────────────────────────────────────

async def test_upsert_calls_execute_with_correct_values():
    conn = make_conn()
    store = make_store(conn)
    contact_id = uuid4()
    handle = ChannelHandle(
        channel_type=ChannelType.EMAIL, handle="a@b.com", preferred=True, verified=False
    )
    await store.upsert(contact_id, handle)
    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args
    sql = call_args.args[0]
    assert "ON CONFLICT" in sql
    assert call_args.args[1] == contact_id
    assert call_args.args[2] == "email"
    assert call_args.args[3] == "a@b.com"
    assert call_args.args[4] is True   # preferred
    assert call_args.args[5] is False  # verified


# ── set_preferred ─────────────────────────────────────────────────────────────

async def test_set_preferred_executes_two_updates():
    conn = make_conn()
    store = make_store(conn)
    await store.set_preferred(uuid4(), ChannelType.EMAIL)
    assert conn.execute.await_count == 2


async def test_set_preferred_uses_transaction():
    conn = make_conn()
    store = make_store(conn)
    await store.set_preferred(uuid4(), ChannelType.EMAIL)
    conn.transaction.assert_called_once()


async def test_set_preferred_unsets_other_types_then_sets_target():
    conn = make_conn()
    store = make_store(conn)
    contact_id = uuid4()
    await store.set_preferred(contact_id, ChannelType.LINKEDIN)
    calls = conn.execute.call_args_list
    # First call: unset preferred for != linkedin
    assert "!=" in calls[0].args[0]
    assert calls[0].args[2] == "linkedin"
    # Second call: set preferred for == linkedin
    assert "preferred = true" in calls[1].args[0]
    assert calls[1].args[2] == "linkedin"


# ── delete ────────────────────────────────────────────────────────────────────

async def test_delete_calls_execute_with_correct_params():
    conn = make_conn()
    store = make_store(conn)
    contact_id = uuid4()
    await store.delete(contact_id, ChannelType.EMAIL, "a@b.com")
    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args
    assert "DELETE" in call_args.args[0]
    assert call_args.args[1] == contact_id
    assert call_args.args[2] == "email"
    assert call_args.args[3] == "a@b.com"
