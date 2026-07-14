"""Tests for the synchronous live NLI rerank (User Story 4, phase 106)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from ze_memory.relevance_config import RelevanceConfig
from ze_memory.retrieval_rerank import live_rerank
from ze_memory.types import Fact


def _fact(value: str) -> Fact:
    return Fact(id=uuid4(), predicate="p", value=value)


# ── T039: live_rerank reorders a bounded candidate set via a mocked NLIClient ─


async def test_live_rerank_reorders_candidates_by_nli_score():
    candidates = [_fact("distractor topic"), _fact("the genuinely relevant fact")]
    nli = AsyncMock()
    nli.scores = AsyncMock(
        return_value=[
            {"entailment": 0.1, "neutral": 0.1, "contradiction": 0.8},
            {"entailment": 0.9, "neutral": 0.05, "contradiction": 0.05},
        ]
    )
    cfg = RelevanceConfig(live_rerank_enabled=True, live_rerank_candidate_limit=20)

    result = await live_rerank(candidates, "query text", nli, cfg)

    assert result[0].value == "the genuinely relevant fact"
    assert result[1].value == "distractor topic"


async def test_live_rerank_bounds_to_candidate_limit_and_appends_tail_unranked():
    candidates = [_fact("a"), _fact("b"), _fact("c")]
    nli = AsyncMock()
    nli.scores = AsyncMock(
        return_value=[
            {"entailment": 0.1, "neutral": 0.0, "contradiction": 0.9},
            {"entailment": 0.9, "neutral": 0.0, "contradiction": 0.1},
        ]
    )
    cfg = RelevanceConfig(live_rerank_enabled=True, live_rerank_candidate_limit=2)

    result = await live_rerank(candidates, "query", nli, cfg)

    assert [f.value for f in result] == ["b", "a", "c"]
    nli.scores.assert_awaited_once()
    assert len(nli.scores.await_args.args[0]) == 2


# ── T040: returns input unchanged (no exception) when disabled/None/timeout/error ─


async def test_live_rerank_returns_unchanged_when_nli_client_none():
    candidates = [_fact("a"), _fact("b")]
    cfg = RelevanceConfig(live_rerank_enabled=True)
    result = await live_rerank(candidates, "query", None, cfg)
    assert result == candidates


async def test_live_rerank_returns_unchanged_when_disabled_by_config():
    candidates = [_fact("a"), _fact("b")]
    nli = AsyncMock()
    cfg = RelevanceConfig(live_rerank_enabled=False)
    result = await live_rerank(candidates, "query", nli, cfg)
    assert result == candidates
    nli.scores.assert_not_called()


async def test_live_rerank_returns_unchanged_on_timeout():
    candidates = [_fact("a"), _fact("b")]

    async def _slow_scores(pairs):
        await asyncio.sleep(10)
        return []

    nli = AsyncMock()
    nli.scores = _slow_scores
    cfg = RelevanceConfig(live_rerank_enabled=True, live_rerank_timeout_ms=1)

    result = await live_rerank(candidates, "query", nli, cfg)
    assert result == candidates


async def test_live_rerank_returns_unchanged_when_client_raises():
    candidates = [_fact("a"), _fact("b")]
    nli = AsyncMock()
    nli.scores = AsyncMock(side_effect=RuntimeError("nli backend down"))
    cfg = RelevanceConfig(live_rerank_enabled=True)

    result = await live_rerank(candidates, "query", nli, cfg)
    assert result == candidates


async def test_live_rerank_empty_candidates_returns_empty():
    nli = AsyncMock()
    cfg = RelevanceConfig(live_rerank_enabled=True)
    result = await live_rerank([], "query", nli, cfg)
    assert result == []
    nli.scores.assert_not_called()


# ── T041: does not read from or write to PostgresRetrievalCacheStore ─────────


async def test_live_rerank_never_touches_retrieval_cache_store(monkeypatch):
    import ze_memory.retrieval_cache as retrieval_cache_module

    def _boom(*args, **kwargs):
        raise AssertionError("live_rerank must not touch PostgresRetrievalCacheStore")

    monkeypatch.setattr(
        retrieval_cache_module.PostgresRetrievalCacheStore, "__init__", _boom
    )
    monkeypatch.setattr(
        retrieval_cache_module.PostgresRetrievalCacheStore, "get", _boom
    )
    monkeypatch.setattr(
        retrieval_cache_module.PostgresRetrievalCacheStore, "upsert", _boom
    )

    candidates = [_fact("a"), _fact("b")]
    nli = AsyncMock()
    nli.scores = AsyncMock(
        return_value=[
            {"entailment": 0.5, "neutral": 0.0, "contradiction": 0.5},
            {"entailment": 0.5, "neutral": 0.0, "contradiction": 0.5},
        ]
    )
    cfg = RelevanceConfig(live_rerank_enabled=True)

    result = await live_rerank(candidates, "query", nli, cfg)
    assert len(result) == 2
