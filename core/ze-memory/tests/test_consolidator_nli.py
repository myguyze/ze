"""Tests for NLI integration in MemoryConsolidator.dedup_facts."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_memory.consolidation_store import PostgresConsolidationStore
from ze_memory.consolidator import MemoryConsolidator


def _store(**overrides):
    s = AsyncMock(spec=PostgresConsolidationStore)
    s.fetch_active_facts = AsyncMock(return_value=[])
    s.mark_contradicted = AsyncMock()
    s.insert_merged_fact = AsyncMock()
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _embedder(vectors: list[list[float]]):
    idx = [0]

    def _encode(_text):
        v = vectors[idx[0] % len(vectors)]
        idx[0] += 1
        return v

    e = MagicMock()
    e.encode = MagicMock(side_effect=_encode)
    return e


def _fact_row(value: str, *, confidence: float = 1.0, created_at: datetime | None = None):
    return {
        "id": uuid4(),
        "predicate": "diet",
        "value": value,
        "confidence": confidence,
        "created_at": created_at or datetime.now(tz=timezone.utc),
    }


def _nli(scores):
    nli = AsyncMock()
    nli.scores = AsyncMock(return_value=scores)
    return nli


def _consolidator(store, embedder, client=None, nli=None):
    return MemoryConsolidator(
        store=store,
        embedder=embedder,
        openrouter_client=client or AsyncMock(),
        nli_client=nli,
    )


async def test_nli_contradiction_marks_older_fact():
    older = _fact_row("User is vegetarian", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _fact_row("User eats meat weekly", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    store = _store(fetch_active_facts=AsyncMock(return_value=[older, newer]))
    vecs = [[1.0, 0.0], [0.75, 0.66]]
    nli = _nli([{"contradiction": 0.9, "neutral": 0.05, "entailment": 0.05}])

    merged = await _consolidator(store, _embedder(vecs), nli=nli).dedup_facts()

    assert merged == 1
    store.mark_contradicted.assert_awaited_once_with(older["id"])
    nli.scores.assert_awaited_once()


async def test_nli_entailment_triggers_llm_merge():
    rows = [_fact_row("likes coffee"), _fact_row("enjoys coffee")]
    store = _store(fetch_active_facts=AsyncMock(return_value=rows))
    vecs = [[1.0, 0.0], [0.87, 0.49]]
    nli = _nli([{"contradiction": 0.05, "neutral": 0.1, "entailment": 0.85}])
    client = AsyncMock()
    client.complete = AsyncMock(return_value="likes and enjoys coffee")

    merged = await _consolidator(store, _embedder(vecs), client=client, nli=nli).dedup_facts()

    assert merged == 1
    client.complete.assert_awaited_once()
    store.insert_merged_fact.assert_awaited_once()


async def test_low_cosine_skips_nli():
    rows = [_fact_row("a"), _fact_row("b")]
    store = _store(fetch_active_facts=AsyncMock(return_value=rows))
    vecs = [[1.0, 0.0], [0.0, 1.0]]
    nli = _nli([])

    merged = await _consolidator(store, _embedder(vecs), nli=nli).dedup_facts()

    assert merged == 0
    nli.scores.assert_not_awaited()


def test_cosine_similarity_parses_pgvector_string():
    from ze_memory.consolidation_store import _cosine_similarity

    assert _cosine_similarity([1.0, 0.0], "[1.0,0.0]") == pytest.approx(1.0)
