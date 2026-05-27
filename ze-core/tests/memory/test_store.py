from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_core.memory.postgres import PostgresMemoryStore as MemoryStore, _cosine_similarity
from ze_core.memory.types import Episode, MemoryContext, UserFact, UserProfile


# ── helpers ───────────────────────────────────────────────────────────────────

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


# ── TestCosineSimilarity ──────────────────────────────────────────────────────

class TestCosineSimilarity:
    def test_identical_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [1.0, 0.0]) - 1.0) < 1e-9

    def test_orthogonal_vectors(self):
        assert abs(_cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-9

    def test_zero_vector_returns_zero(self):
        assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ── TestGetContext ────────────────────────────────────────────────────────────

class TestGetContext:
    async def test_empty_store_returns_empty_context(self):
        store, _ = _store()
        result = await store.get_context([0.1, 0.2], "a")
        assert isinstance(result, MemoryContext)
        assert result.facts == []
        assert result.episodes == []
        assert result.profile is None

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
        assert result.facts[0].value == "Alice"

    async def test_token_budget_limits_facts(self):
        # Each fact value is 400 chars → 100 tokens; budget is 200 → max 2
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [_fact_row(f"k{i}", "x" * 400) for i in range(5)],
            [],
        ])
        store, _ = _store(conn=conn)
        result = await store.get_context([0.1], "a", token_budget={"facts": 200, "episodes": 500})
        assert len(result.facts) == 2

    async def test_profile_returned_when_fields_present(self):
        conn = _conn()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value={
            "preferences": "coffee",
            "habits": "morning run",
            "topics": "tech",
            "relationships": "wife: Ana",
            "goals": "ship ze-core",
            "updated_at": _now(),
            "version": 3,
        })
        store, _ = _store(conn=conn)
        result = await store.get_context([0.1], "a")
        assert result.profile is not None
        assert result.profile.preferences == "coffee"
        assert result.profile.version == 3

    async def test_profile_none_when_all_empty_strings(self):
        conn = _conn()
        conn.fetch = AsyncMock(return_value=[])
        conn.fetchrow = AsyncMock(return_value={
            "preferences": "", "habits": "", "topics": "",
            "relationships": "", "goals": "",
            "updated_at": _now(), "version": 0,
        })
        store, _ = _store(conn=conn)
        result = await store.get_context([0.1], "a")
        assert result.profile is None

    async def test_missing_summaries_generated_and_cached(self):
        ep_id = uuid4()
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [],
            [_episode_row(summary=None)],
        ])
        client = _client(response="generated summary")
        store, _ = _store(conn=conn, client=client)
        result = await store.get_context([0.1], "a")
        assert result.episodes[0].summary == "generated summary"
        # Verify UPDATE was called to cache the summary
        conn.execute.assert_awaited()

    async def test_episodes_with_existing_summary_not_regenerated(self):
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [],
            [_episode_row(summary="existing summary")],
        ])
        client = _client()
        store, _ = _store(conn=conn, client=client)
        await store.get_context([0.1], "a")
        client.complete.assert_not_awaited()

    async def test_token_estimate_set(self):
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [_fact_row("k", "hello")],  # 5 chars → 1 token
            [],
        ])
        store, _ = _store(conn=conn)
        result = await store.get_context([0.1], "a")
        assert result.token_estimate > 0


# ── TestWriteEpisode ──────────────────────────────────────────────────────────

class TestWriteEpisode:
    async def test_inserts_row(self):
        conn = _conn()
        store, _ = _store(conn=conn)
        await store.write_episode("agent", "prompt", "response", [0.1, 0.2])
        conn.execute.assert_awaited_once()

    async def test_swallows_db_error(self):
        conn = _conn()
        conn.execute = AsyncMock(side_effect=Exception("db down"))
        store, _ = _store(conn=conn)
        # Must not raise
        await store.write_episode("agent", "prompt", "response", [0.1, 0.2])

    async def test_embedding_converted_to_list(self):
        conn = _conn()
        store, _ = _store(conn=conn)
        vec = MagicMock()
        vec.tolist = MagicMock(return_value=[0.5, 0.5])
        await store.write_episode("a", "p", "r", vec)
        call_args = conn.execute.call_args[0]
        assert [0.5, 0.5] in call_args


# ── TestProposeFacts ──────────────────────────────────────────────────────────

class TestProposeFacts:
    async def test_inserts_each_fact(self):
        conn = _conn()
        conn.fetch = AsyncMock(return_value=[])
        store, _ = _store(conn=conn)
        facts = [UserFact(key="k1", value="v1"), UserFact(key="k2", value="v2")]
        await store.propose_facts(facts)
        # Each fact triggers: exact key check, semantic check, insert → at minimum 2 executes
        assert conn.execute.await_count >= 2

    async def test_continues_after_single_fact_failure(self):
        conn = _conn()
        # First fetch returns an existing row that causes a cascade update failure
        call_count = 0

        async def _fetch(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return []

        conn.fetch = _fetch
        conn.execute = AsyncMock(side_effect=[Exception("fail on first insert"), None])
        store, _ = _store(conn=conn)
        facts = [UserFact(key="k1", value="v1"), UserFact(key="k2", value="v2")]
        await store.propose_facts(facts)  # should not raise

    async def test_exact_key_match_marks_contradicted(self):
        existing_id = uuid4()
        conn = _conn()
        conn.fetch = AsyncMock(side_effect=[
            [{"id": existing_id}],  # exact key match
            [],                      # semantic search
        ])
        store, _ = _store(conn=conn)
        await store.propose_facts([UserFact(key="same_key", value="new value")])
        # Verify contradicted = true update was called for the existing fact
        update_calls = [c for c in conn.execute.await_args_list if "contradicted = true" in str(c)]
        assert len(update_calls) >= 1


# ── TestGetProfile ────────────────────────────────────────────────────────────

class TestGetProfile:
    async def test_returns_none_when_no_row(self):
        conn = _conn()
        conn.fetchrow = AsyncMock(return_value=None)
        store, _ = _store(conn=conn)
        assert await store.get_profile() is None

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

    async def test_returns_none_when_all_empty(self):
        conn = _conn()
        conn.fetchrow = AsyncMock(return_value={
            "preferences": "", "habits": "", "topics": "",
            "relationships": "", "goals": "",
            "updated_at": _now(), "version": 0,
        })
        store, _ = _store(conn=conn)
        assert await store.get_profile() is None


# ── TestSettingsAccess ────────────────────────────────────────────────────────

class TestSettingsAccess:
    async def test_dict_settings_used_for_threshold(self):
        settings = {"memory": {"contradiction_threshold": 0.99}}
        conn = _conn()
        conn.fetch = AsyncMock(return_value=[])
        store, _ = _store(conn=conn, settings=settings)
        # The store should read 0.99 from settings — verified indirectly by
        # checking that no contradiction update fires for low-similarity pair
        emb_a = [1.0, 0.0]
        emb_b = [0.0, 1.0]
        embedder = MagicMock()
        embedder.encode = MagicMock(side_effect=[emb_a, emb_b])
        store._embedder = embedder
        await store.propose_facts([UserFact(key="x", value="orthogonal")])
        # cosine_similarity([1,0],[0,1]) = 0.0 < 0.99 → no contradiction update
        update_calls = [c for c in conn.execute.await_args_list if "contradicted = true" in str(c)]
        assert len(update_calls) == 0

    def test_synthesis_model_from_dict_settings(self):
        settings = {"models": {"synthesis": "openai/gpt-4"}}
        store = MemoryStore(
            pool=MagicMock(), embedder=MagicMock(),
            openrouter_client=MagicMock(), settings=settings,
        )
        assert store._synthesis_model() == "openai/gpt-4"

    def test_synthesis_model_default_when_no_settings(self):
        store = MemoryStore(
            pool=MagicMock(), embedder=MagicMock(),
            openrouter_client=MagicMock(), settings=None,
        )
        assert store._synthesis_model() == "anthropic/claude-haiku-4-5"
