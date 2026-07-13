"""Tests for retrieval_cache.py — session-scoped NLI retrieval cache."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_memory.retrieval_cache import (
    PostgresRetrievalCacheStore,
    query_hash,
)


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def test_query_hash_is_stable_and_normalized():
    h1 = query_hash("companion", "  Hello World  ")
    h2 = query_hash("companion", "hello world")
    h3 = query_hash("research", "hello world")
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 32


async def test_cache_get_returns_none_when_missing():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    store = PostgresRetrievalCacheStore(pool)
    assert await store.get("sess-1", "abc123") is None


async def test_cache_upsert_and_get_roundtrip():
    fact_id = uuid4()
    summary_id = uuid4()
    created = datetime.now(timezone.utc)
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            "session_id": "sess-1",
            "query_hash": "hash1",
            "fact_ranked_ids": [fact_id],
            "summary_ranked_ids": [summary_id],
            "created_at": created,
        }
    )
    conn.execute = AsyncMock(return_value="INSERT 1")
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    store = PostgresRetrievalCacheStore(pool)
    await store.upsert("sess-1", "hash1", [fact_id], [summary_id])
    entry = await store.get("sess-1", "hash1")

    assert entry is not None
    assert entry.session_id == "sess-1"
    assert entry.fact_ranked_ids == [fact_id]
    assert entry.summary_ranked_ids == [summary_id]
    conn.execute.assert_awaited_once()


async def test_expire_older_than_returns_deleted_count():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value="DELETE 3")
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    store = PostgresRetrievalCacheStore(pool)
    deleted = await store.expire_older_than(days=1)

    assert deleted == 3
    conn.execute.assert_awaited_once()
