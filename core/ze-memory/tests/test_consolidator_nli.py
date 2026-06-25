"""Tests for NLI integration in MemoryConsolidator.dedup_facts."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
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


def _consolidator(store, embedder, client=None):
    return MemoryConsolidator(
        store=store,
        embedder=embedder,
        openrouter_client=client or AsyncMock(),
    )


@patch("ze_memory.consolidator.nli_scores_async", new_callable=AsyncMock)
async def test_nli_contradiction_marks_older_fact(mock_nli):
    older = _fact_row("User is vegetarian", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    newer = _fact_row("User eats meat weekly", created_at=datetime(2026, 6, 1, tzinfo=timezone.utc))
    store = _store(fetch_active_facts=AsyncMock(return_value=[older, newer]))
    vecs = [[1.0, 0.0], [0.75, 0.66]]
    mock_nli.return_value = [{"contradiction": 0.9, "neutral": 0.05, "entailment": 0.05}]

    merged = await _consolidator(store, _embedder(vecs)).dedup_facts()

    assert merged == 1
    store.mark_contradicted.assert_awaited_once_with(older["id"])
    mock_nli.assert_awaited_once()


@patch("ze_memory.consolidator.nli_scores_async", new_callable=AsyncMock)
async def test_nli_entailment_triggers_llm_merge(mock_nli):
    rows = [_fact_row("likes coffee"), _fact_row("enjoys coffee")]
    store = _store(fetch_active_facts=AsyncMock(return_value=rows))
    vecs = [[1.0, 0.0], [0.87, 0.49]]
    mock_nli.return_value = [{"contradiction": 0.05, "neutral": 0.1, "entailment": 0.85}]
    client = AsyncMock()
    client.complete = AsyncMock(return_value="likes and enjoys coffee")

    merged = await _consolidator(store, _embedder(vecs), client=client).dedup_facts()

    assert merged == 1
    client.complete.assert_awaited_once()
    store.insert_merged_fact.assert_awaited_once()


@patch("ze_memory.consolidator.nli_scores_async", new_callable=AsyncMock)
async def test_low_cosine_skips_nli(mock_nli):
    rows = [_fact_row("a"), _fact_row("b")]
    store = _store(fetch_active_facts=AsyncMock(return_value=rows))
    vecs = [[1.0, 0.0], [0.0, 1.0]]

    merged = await _consolidator(store, _embedder(vecs)).dedup_facts()

    assert merged == 0
    mock_nli.assert_not_awaited()
