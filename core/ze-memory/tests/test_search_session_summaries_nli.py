"""Tests for NLI re-ranking in search_session_summaries."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ze_memory.retriever import PostgresMemoryStore


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _summary_row(session_id: str, summary: str):
    return {
        "id": uuid4(),
        "session_id": session_id,
        "summary": summary,
        "episode_count": 3,
        "last_turn_at": None,
        "created_at": None,
        "summary_updated_at": None,
    }


@patch("ze_memory.retriever.nli_scores_async", new_callable=AsyncMock)
async def test_search_session_summaries_reranks_by_nli(mock_nli):
    rows = [
        _summary_row("s1", "Discussed project deadlines"),
        _summary_row("s2", "User prefers tea over coffee"),
    ]
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=rows)

    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = MagicMock()
    store._pool.acquire = MagicMock(return_value=_async_ctx(conn))
    store._settings = {
        "memory": {
            "nli_retrieval_rerank": True,
            "nli_rerank_candidate_multiplier": 2,
            "nli_rerank_min_candidates": 2,
        }
    }

    mock_nli.return_value = [
        {"contradiction": 0.1, "neutral": 0.1, "entailment": 0.2},
        {"contradiction": 0.1, "neutral": 0.1, "entailment": 0.9},
    ]

    results = await store.search_session_summaries(
        [0.1] * 384,
        limit=1,
        query_text="What does the user drink?",
    )

    assert len(results) == 1
    assert results[0].session_id == "s2"
    mock_nli.assert_awaited_once()
