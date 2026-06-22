from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from ze_core.conversation.sessions import PostgresSessionStore


def _make_pool_mock(rows=None, fetchrow=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows or [])
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.execute = AsyncMock()

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


def _make_session_row(session_id: str = "thread-1"):
    row = MagicMock()
    now = datetime.now(timezone.utc)
    row.__getitem__ = lambda self, key: {
        "id": session_id,
        "title": "Test",
        "preview": "Hello",
        "created_at": now,
        "last_active_at": now,
    }[key]
    return row


async def test_list_all_returns_sessions():
    row = _make_session_row()
    pool, conn = _make_pool_mock(rows=[row])
    store = PostgresSessionStore(pool=pool)

    results = await store.list_all(limit=10)

    assert len(results) == 1
    assert results[0].id == "thread-1"
    conn.fetch.assert_called_once()


async def test_get_returns_session_when_found():
    row = _make_session_row("thread-2")
    pool, conn = _make_pool_mock(fetchrow=row)
    store = PostgresSessionStore(pool=pool)

    result = await store.get("thread-2")

    assert result is not None
    assert result.id == "thread-2"
    conn.fetchrow.assert_called_once()


async def test_get_returns_none_when_missing():
    pool, conn = _make_pool_mock(fetchrow=None)
    store = PostgresSessionStore(pool=pool)

    result = await store.get("missing")

    assert result is None


async def test_upsert_executes_insert():
    pool, conn = _make_pool_mock()
    store = PostgresSessionStore(pool=pool)

    await store.upsert("thread-3", title="Title", preview="Preview")

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO sessions" in sql
