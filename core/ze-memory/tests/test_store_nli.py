"""Tests for write-time NLI contradiction detection."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_memory.retriever import PostgresMemoryStore
from ze_memory.types import Fact


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_store(conn):
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = MagicMock()
    store._pool.acquire = MagicMock(return_value=_async_ctx(conn))
    store._embedder = MagicMock()
    store._embedder.encode = MagicMock(return_value=[1.0, 0.0])
    store._client = None
    store._graph_store = None
    store._traversal = None
    store._settings = {"memory": {"nli_write_time_check": True}}
    return store


@patch("ze_memory.retriever.nli_scores_async", new_callable=AsyncMock)
async def test_semantic_contradiction_marks_cross_predicate_fact(mock_nli):
    existing_id = uuid4()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {"id": existing_id, "value": "User is vegetarian", "embedding": [0.75, 0.66]},
    ])
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    mock_nli.return_value = [{"contradiction": 0.9, "neutral": 0.05, "entailment": 0.05}]

    store = _make_store(conn)
    subject_id = uuid4()
    fact = Fact(
        id=None,
        subject_id=subject_id,
        predicate="eating_habits",
        value="User eats meat weekly",
        object_text="meat",
        confidence=0.9,
    )
    await store._write_fact_with_contradiction_check(fact)

    update_calls = [c for c in conn.execute.await_args_list if "contradicted = true" in c[0][0]]
    assert len(update_calls) >= 2
    mock_nli.assert_awaited_once()


@patch("ze_memory.retriever.nli_scores_async", new_callable=AsyncMock)
async def test_write_time_nli_disabled_skips_semantic_check(mock_nli):
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})

    store = _make_store(conn)
    store._settings = {"memory": {"nli_write_time_check": False}}
    fact = Fact(
        id=None,
        subject_id=uuid4(),
        predicate="diet",
        value="vegetarian",
        object_text="vegetarian",
        confidence=0.9,
    )
    await store._write_fact_with_contradiction_check(fact)

    conn.fetch.assert_not_awaited()
    mock_nli.assert_not_awaited()
