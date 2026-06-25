"""Tests for retrieve() session-cached NLI re-ranking."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ze_agents.types import RetrievalRequest
from ze_memory.retriever import PostgresMemoryStore
from ze_memory.types import Fact, MemoryContext, RetrievalCacheEntry


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_store(*, settings: dict | None = None):
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = MagicMock()
    store._settings = settings or {
        "memory": {
            "nli_retrieval_rerank": True,
            "nli_rerank_candidate_multiplier": 2,
            "nli_rerank_min_candidates": 2,
        }
    }
    store._registry = MagicMock()
    store._traversal = None
    store._retrieval_cache = AsyncMock()
    store._retrieval_cache.get = AsyncMock(return_value=None)
    return store


def _request(*, module: str = "companion", query: str = "what is my schedule"):
    return RetrievalRequest(
        module=module,
        agent=module,
        query_text=query,
        query_embedding=[0.1, 0.2, 0.3],
        current_session_id="sess-abc",
    )


@patch("ze_memory.retriever.fire_and_forget")
async def test_retrieve_schedules_cache_build_on_miss(mock_ff):
    store = _make_store()
    policy_ctx = MemoryContext(facts=[Fact(predicate="x", value="y")])
    policy = AsyncMock()
    policy.retrieve = AsyncMock(return_value=policy_ctx)
    store._registry.for_module = MagicMock(return_value=policy)

    result = await store.retrieve(_request())

    assert result is policy_ctx
    mock_ff.assert_called_once()
    store._retrieval_cache.get.assert_awaited_once()


@patch("ze_memory.retriever.fire_and_forget")
@patch("ze_memory.retriever.fetch_facts_by_ids", new_callable=AsyncMock)
async def test_retrieve_applies_cached_fact_order(mock_fetch_facts, mock_ff):
    id_first, id_second = uuid4(), uuid4()
    cached = RetrievalCacheEntry(
        session_id="sess-abc",
        query_hash="hash",
        fact_ranked_ids=[id_first, id_second],
        summary_ranked_ids=[],
        created_at=datetime.now(timezone.utc),
    )
    store = _make_store()
    store._retrieval_cache.get = AsyncMock(return_value=cached)

    policy_ctx = MemoryContext(
        facts=[
            Fact(id=id_second, predicate="b", value="second"),
            Fact(id=id_first, predicate="a", value="first"),
        ]
    )
    policy = AsyncMock()
    policy.retrieve = AsyncMock(return_value=policy_ctx)
    store._registry.for_module = MagicMock(return_value=policy)

    mock_fetch_facts.return_value = [
        {"id": id_first, "subject_id": None, "predicate": "a", "object_text": None,
         "object_id": None, "value": "first", "confidence": 1.0, "reviewed": False,
         "contradicted": False, "source_episode_id": None, "source_refs": []},
        {"id": id_second, "subject_id": None, "predicate": "b", "object_text": None,
         "object_id": None, "value": "second", "confidence": 1.0, "reviewed": False,
         "contradicted": False, "source_episode_id": None, "source_refs": []},
    ]

    result = await store.retrieve(_request())

    mock_fetch_facts.assert_awaited_once_with(store._pool, [id_first, id_second])
    assert result.facts[0].id == id_first
    assert result.facts[1].id == id_second
    mock_ff.assert_called_once()


@patch("ze_memory.retriever.fire_and_forget")
async def test_retrieve_skips_rerank_when_disabled(mock_ff):
    store = _make_store(
        settings={"memory": {"nli_retrieval_rerank": False}},
    )
    policy_ctx = MemoryContext()
    policy = AsyncMock()
    policy.retrieve = AsyncMock(return_value=policy_ctx)
    store._registry.for_module = MagicMock(return_value=policy)

    await store.retrieve(_request())

    store._retrieval_cache.get.assert_not_awaited()
    mock_ff.assert_not_called()


@patch("ze_memory.retriever.fire_and_forget")
async def test_retrieve_skips_excluded_module(mock_ff):
    store = _make_store()
    policy_ctx = MemoryContext()
    policy = AsyncMock()
    policy.retrieve = AsyncMock(return_value=policy_ctx)
    store._registry.for_module = MagicMock(return_value=policy)

    await store.retrieve(_request(module="planner"))

    store._retrieval_cache.get.assert_not_awaited()
    mock_ff.assert_not_called()
