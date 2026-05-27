"""Memory store tests — ze-core PostgresMemoryStore via ze.memory.store."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np
import pytest

from ze.memory.store import MemoryStore, _cosine_similarity, _tokens, _vec
from ze.memory.types import Episode, MemoryContext, UserFact, UserProfile


def _conn():
    c = AsyncMock()
    c.fetch = AsyncMock(return_value=[])
    c.fetchrow = AsyncMock(return_value=None)
    c.execute = AsyncMock(return_value="UPDATE 0")
    return c


def _pool(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=cm)
    return pool


def _embedder(vec=None):
    v = vec or [0.1, 0.2, 0.3]
    e = MagicMock()
    e.encode = MagicMock(return_value=v)
    return e


def _client(response="summary"):
    c = AsyncMock()
    c.complete = AsyncMock(return_value=response)
    return c


def _store(conn=None, vec=None, client=None, settings=None):
    c = conn or _conn()
    return MemoryStore(
        pool=_pool(c),
        embedder=_embedder(vec),
        openrouter_client=client or _client(),
        settings=settings,
    ), c


def _now():
    return datetime.now(timezone.utc)


def _fact_row(key="k", value="v", agent="global", confidence=1.0):
    return {
        "id": uuid4(),
        "key": key,
        "value": value,
        "agent": agent,
        "confidence": confidence,
        "reviewed": False,
        "contradicted": False,
        "updated_at": _now(),
    }


def _episode_row(summary=None, response="resp"):
    return {
        "id": uuid4(),
        "agent": "a",
        "prompt": "p",
        "response": response,
        "summary": summary,
        "is_archive": False,
        "created_at": _now(),
    }


def test_vec_formats_numpy_array():
    arr = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    result = _vec(arr)
    assert result.startswith("[")
    assert "0.10000000" in result


def test_tokens_approximates_length():
    assert _tokens("hello world") == 2
    assert _tokens("") == 0
    assert _tokens("a" * 400) == 100


class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9


class TestGetContext:
    async def test_empty_store_returns_empty_context(self):
        store, _ = _store()
        result = await store.get_context([0.1, 0.2], "a")
        assert isinstance(result, MemoryContext)
        assert result.facts == []
        assert result.episodes == []

    async def test_facts_built_from_rows(self):
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [_fact_row("name", "Alice")],
            [],
        ])
        store, _ = _store(conn=conn)
        result = await store.get_context([0.1], "a")
        assert len(result.facts) == 1
        assert result.facts[0].key == "name"


class TestWriteEpisode:
    async def test_inserts_row(self):
        conn = _conn()
        store, _ = _store(conn=conn)
        await store.write_episode("agent", "prompt", "response", [0.1, 0.2])
        conn.execute.assert_awaited_once()


class TestProposeFacts:
    async def test_exact_key_match_marks_contradicted(self):
        existing_id = uuid4()
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [{"id": existing_id}],
            [],
        ])
        store, _ = _store(conn=conn)
        await store.propose_facts([UserFact(key="same_key", value="new value")])
        update_calls = [c for c in conn.execute.await_args_list if "contradicted = true" in str(c)]
        assert len(update_calls) >= 1


class TestGetProfile:
    async def test_returns_profile_from_row(self):
        conn = _conn()
        conn.fetchrow = AsyncMock(return_value={
            "preferences": "p", "habits": "h", "topics": "t",
            "relationships": "r", "goals": "g",
            "updated_at": _now(), "version": 1,
        })
        store, _ = _store(conn=conn)
        result = await store.get_profile()
        assert isinstance(result, UserProfile)
        assert result.version == 1
