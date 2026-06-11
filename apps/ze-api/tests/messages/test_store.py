from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_core.messages.store import PostgresMessageStore
from ze_core.messages.types import Message


def _make_message(**kwargs) -> Message:
    return Message(
        id=kwargs.get("id", uuid4()),
        role=kwargs.get("role", "assistant"),
        text=kwargs.get("text", "Hello"),
        components=kwargs.get("components", []),
        read=kwargs.get("read", False),
        created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
        thread_id=kwargs.get("thread_id", None),
    )


def _make_pool_mock(rows=None, execute_side_effect=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.execute = AsyncMock(side_effect=execute_side_effect)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncContextManagerMock(conn))
    return pool, conn


class _AsyncContextManagerMock:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        pass


def _make_row(msg: Message):
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": msg.id,
        "role": msg.role,
        "text": msg.text,
        "components": json.dumps(msg.components),
        "read": msg.read,
        "thread_id": msg.thread_id,
        "created_at": msg.created_at,
    }[key]
    return row


async def test_save_writes_correct_row():
    pool, conn = _make_pool_mock()
    store = PostgresMessageStore(pool=pool)
    msg = _make_message(text="Hello", role="assistant")

    await store.save(msg)

    conn.execute.assert_called_once()
    call_args = conn.execute.call_args[0]
    assert msg.id in call_args
    assert "assistant" in call_args
    assert "Hello" in call_args


async def test_list_since_returns_ascending_order():
    msg1 = _make_message(id=uuid4())
    msg2 = _make_message(id=uuid4())
    pool, conn = _make_pool_mock(rows=[_make_row(msg1), _make_row(msg2)])
    store = PostgresMessageStore(pool=pool)

    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    results = await store.list_since(since, limit=10)

    assert len(results) == 2
    conn.fetch.assert_called_once()
    _, limit_arg = conn.fetch.call_args[0][1], conn.fetch.call_args[0][2]
    assert limit_arg == 10


async def test_mark_read_flips_read_flag():
    pool, conn = _make_pool_mock()
    store = PostgresMessageStore(pool=pool)
    ids = [uuid4(), uuid4()]

    await store.mark_read(ids)

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "read = TRUE" in sql


async def test_mark_read_noop_for_empty_list():
    pool, conn = _make_pool_mock()
    store = PostgresMessageStore(pool=pool)

    await store.mark_read([])

    conn.execute.assert_not_called()


async def test_list_unread_excludes_read_messages():
    msg = _make_message(read=False)
    pool, conn = _make_pool_mock(rows=[_make_row(msg)])
    store = PostgresMessageStore(pool=pool)

    results = await store.list_unread()

    assert len(results) == 1
    sql = conn.fetch.call_args[0][0]
    assert "NOT read" in sql
