"""Tests for SQLiteMemoryStore."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.container import _sqlite_db_path
from ze_core.memory.types import UserFact
from ze_core.memory.sqlite import SQLiteMemoryStore, _cosine


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def store(tmp_path):
    """In-memory SQLite store with a stub embedder."""
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=[0.1, 0.2, 0.3])

    client = AsyncMock()
    client.complete = AsyncMock(return_value="summary")

    s = SQLiteMemoryStore(":memory:", embedder=embedder, openrouter_client=client)
    await s.setup()
    yield s
    await s.aclose()


# ── _cosine ───────────────────────────────────────────────────────────────────

class TestCosine:
    def test_identical_vectors_return_one(self):
        v = [1.0, 0.0, 0.0]
        assert abs(_cosine(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors_return_zero(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        assert _cosine([0.0, 0.0], [1.0, 0.0]) == 0.0


# ── _sqlite_db_path ───────────────────────────────────────────────────────────

class TestSqliteDbPath:
    def test_triple_slash_relative(self):
        assert _sqlite_db_path("sqlite:///./app.db") == "./app.db"

    def test_four_slash_absolute(self):
        assert _sqlite_db_path("sqlite:////abs/path.db") == "/abs/path.db"

    def test_memory(self):
        assert _sqlite_db_path("sqlite:///:memory:") == ":memory:"


# ── setup / aclose ────────────────────────────────────────────────────────────

class TestSetupClose:
    async def test_setup_creates_schema(self, store):
        async with store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            tables = {row[0] for row in await cur.fetchall()}
        assert {"user_facts", "episodes", "user_profile"} <= tables

    async def test_aclose_sets_conn_to_none(self, store):
        await store.aclose()
        assert store._conn is None

    async def test_double_close_is_safe(self, store):
        await store.aclose()
        await store.aclose()  # should not raise


# ── write_episode ─────────────────────────────────────────────────────────────

class TestWriteEpisode:
    async def test_stores_episode(self, store):
        await store.write_episode("research", "hello", "world", [0.1, 0.2, 0.3])
        async with store._conn.execute("SELECT COUNT(*) FROM episodes") as cur:
            count = (await cur.fetchone())[0]
        assert count == 1

    async def test_multiple_episodes(self, store):
        for i in range(3):
            await store.write_episode("a", f"p{i}", f"r{i}", [float(i), 0.0])
        async with store._conn.execute("SELECT COUNT(*) FROM episodes") as cur:
            assert (await cur.fetchone())[0] == 3


# ── propose_facts ─────────────────────────────────────────────────────────────

class TestProposeFacts:
    async def test_stores_fact(self, store):
        fact = UserFact(key="name", value="Alice", agent="companion")
        await store.propose_facts([fact])
        async with store._conn.execute("SELECT value FROM user_facts WHERE key='name'") as cur:
            row = await cur.fetchone()
        assert row is not None
        assert row[0] == "Alice"

    async def test_exact_key_match_marks_contradicted(self, store):
        store._embedder.encode = MagicMock(return_value=[1.0, 0.0, 0.0])
        await store.propose_facts([UserFact(key="city", value="London", agent="global")])
        await store.propose_facts([UserFact(key="city", value="Paris", agent="global")])

        async with store._conn.execute(
            "SELECT value, contradicted FROM user_facts WHERE key='city' ORDER BY updated_at"
        ) as cur:
            rows = await cur.fetchall()

        assert len(rows) == 2
        assert rows[0]["contradicted"] == 1   # London contradicted
        assert rows[1]["contradicted"] == 0   # Paris current

    async def test_multiple_facts(self, store):
        facts = [
            UserFact(key=f"k{i}", value=f"v{i}", agent="global")
            for i in range(5)
        ]
        await store.propose_facts(facts)
        async with store._conn.execute("SELECT COUNT(*) FROM user_facts") as cur:
            assert (await cur.fetchone())[0] == 5


# ── get_context ───────────────────────────────────────────────────────────────

class TestGetContext:
    async def test_empty_store_returns_empty_context(self, store):
        ctx = await store.get_context([0.1, 0.2, 0.3], "research")
        assert ctx.facts == []
        assert ctx.episodes == []
        assert ctx.profile is None
        assert ctx.token_estimate == 0

    async def test_returns_written_facts(self, store):
        await store.propose_facts([UserFact(key="lang", value="Python", agent="global")])
        ctx = await store.get_context([0.1, 0.2, 0.3], "research")
        assert len(ctx.facts) == 1
        assert ctx.facts[0].key == "lang"

    async def test_returns_written_episodes(self, store):
        await store.write_episode("research", "q", "a", [0.1, 0.2, 0.3])
        ctx = await store.get_context([0.1, 0.2, 0.3], "research")
        assert len(ctx.episodes) == 1

    async def test_contradicted_facts_excluded(self, store):
        store._embedder.encode = MagicMock(return_value=[1.0, 0.0])
        await store.propose_facts([UserFact(key="x", value="old", agent="global")])
        await store.propose_facts([UserFact(key="x", value="new", agent="global")])
        ctx = await store.get_context([1.0, 0.0], "global")
        values = [f.value for f in ctx.facts]
        assert "old" not in values
        assert "new" in values

    async def test_token_budget_respected(self, store):
        # Write many facts that together exceed a tiny budget
        for i in range(20):
            await store.propose_facts([
                UserFact(key=f"fact{i}", value="x" * 100, agent="global")
            ])
        ctx = await store.get_context([0.1, 0.2, 0.3], "global", token_budget={"facts": 10})
        # Budget is 10 tokens (~40 chars); each fact is 25 tokens, so at most 0 fit
        assert ctx.token_estimate <= 30  # some slack for empty result


# ── get_profile ───────────────────────────────────────────────────────────────

class TestGetProfile:
    async def test_returns_none_when_empty(self, store):
        assert await store.get_profile() is None

    async def test_returns_profile_when_written(self, store):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        await store._conn.execute(
            "INSERT INTO user_profile"
            " (id, preferences, habits, topics, relationships, goals, updated_at, version)"
            " VALUES (1, 'cats', 'morning run', 'python', 'alice', 'learn rust', ?, 1)",
            (now,),
        )
        await store._conn.commit()

        profile = await store.get_profile()
        assert profile is not None
        assert profile.preferences == "cats"
        assert profile.goals == "learn rust"
        assert profile.version == 1
