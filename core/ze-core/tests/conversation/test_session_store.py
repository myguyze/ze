from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


from ze_core.conversation.sessions import PostgresSessionStore, SessionTitleGenerator


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


def _make_session_row(session_id: str = "thread-1", title_source: str | None = "user"):
    row = MagicMock()
    now = datetime.now(timezone.utc)
    row.__getitem__ = lambda self, key: {
        "id": session_id,
        "title": "Test",
        "preview": "Hello",
        "title_source": title_source,
        "created_at": now,
        "last_active_at": now,
    }[key]
    return row


async def test_list_page_returns_sessions():
    row = _make_session_row()
    pool, conn = _make_pool_mock(rows=[row])
    store = PostgresSessionStore(pool=pool)

    page = await store.list_page(limit=10)

    assert len(page.items) == 1
    assert page.items[0].id == "thread-1"
    assert page.next_before is None
    conn.fetch.assert_called_once()


async def test_list_page_sets_next_before_when_full():
    rows = [_make_session_row(f"thread-{i}") for i in range(3)]
    pool, conn = _make_pool_mock(rows=rows)
    store = PostgresSessionStore(pool=pool)

    page = await store.list_page(limit=3)

    assert len(page.items) == 3
    assert page.next_before == page.items[-1].last_active_at


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

    await store.upsert(
        "thread-3", title="Title", preview="Preview", title_source="user"
    )

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO sessions" in sql
    assert "title_source" in sql


async def test_search_returns_empty_for_short_query():
    pool, conn = _make_pool_mock()
    store = PostgresSessionStore(pool=pool)

    results = await store.search("a")

    assert results == []
    conn.fetchrow.assert_not_called()


async def test_search_uses_fts_when_tsquery_valid():
    tsq_row = MagicMock()
    tsq_row.__getitem__ = lambda self, key: {"tsq": "calendar"}[key]
    hit_row = _make_session_row()
    hit_row.__getitem__ = lambda self, key: {
        "id": "thread-1",
        "title": "Calendar",
        "preview": "Tomorrow",
        "title_source": "generated",
        "created_at": datetime.now(timezone.utc),
        "last_active_at": datetime.now(timezone.utc),
        "match_source": "message",
        "rank": 0.9,
        "snippet": "your <b>calendar</b> tomorrow",
    }[key]

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=tsq_row)
    conn.fetch = AsyncMock(return_value=[hit_row])
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncContextManagerMock(conn))
    store = PostgresSessionStore(pool=pool)

    results = await store.search("calendar")

    assert len(results) == 1
    assert results[0].match_source == "message"
    assert results[0].snippet == "your <b>calendar</b> tomorrow"


async def test_title_generator_truncates_to_eight_words():
    client = AsyncMock()
    client.complete = AsyncMock(
        return_value="Plan a long multi word title that exceeds the maximum allowed length"
    )
    generator = SessionTitleGenerator(client, "test-model")

    title = await generator.generate(user_text="Help me plan", assistant_text="Sure")

    assert len(title.split()) == 8
    client.complete.assert_awaited_once()
