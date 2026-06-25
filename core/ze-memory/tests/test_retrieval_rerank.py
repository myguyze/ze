"""Tests for retrieval_rerank.py — NLI row reranking helpers."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ze_memory.retrieval_rerank import nli_rank_score, rerank_row_ids, rerank_rows


def test_nli_rank_score():
    assert nli_rank_score({"entailment": 0.8, "neutral": 0.1, "contradiction": 0.1}) == pytest.approx(0.85)
    assert nli_rank_score(None) == 0.0


async def test_rerank_rows_orders_by_nli_score():
    rows = [
        {"id": uuid4(), "value": "low relevance"},
        {"id": uuid4(), "value": "high relevance"},
    ]
    nli = AsyncMock()
    nli.scores = AsyncMock(return_value=[
        {"contradiction": 0.1, "neutral": 0.1, "entailment": 0.2},
        {"contradiction": 0.05, "neutral": 0.05, "entailment": 0.9},
    ])

    ordered = await rerank_rows(
        rows, "value", "user query", min_candidates=2, nli_client=nli
    )

    assert ordered[0]["value"] == "high relevance"
    assert ordered[1]["value"] == "low relevance"


async def test_rerank_rows_skips_when_below_min_candidates():
    rows = [{"id": uuid4(), "value": "only one"}]
    ordered = await rerank_rows(rows, "value", "query", min_candidates=5)
    assert ordered == rows


async def test_rerank_row_ids_returns_ordered_uuids():
    id_a, id_b = uuid4(), uuid4()
    rows = [
        {"id": id_a, "value": "a"},
        {"id": id_b, "value": "b"},
    ]
    nli = AsyncMock()
    nli.scores = AsyncMock(return_value=[
        {"contradiction": 0.1, "neutral": 0.1, "entailment": 0.9},
        {"contradiction": 0.1, "neutral": 0.1, "entailment": 0.1},
    ])

    ids = await rerank_row_ids(rows, "value", "query", min_candidates=2, nli_client=nli)

    assert ids == [id_a, id_b]
