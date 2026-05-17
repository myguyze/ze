import pathlib
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import numpy as np

from ze.memory.store import MemoryStore, _tokens, _vec
from ze.memory.types import MemoryContext, UserFact
from ze.settings import Settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    from ze.settings import get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_embedder():
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=np.zeros(384))
    return embedder


def make_store(pool=None, embedder=None, client=None, settings=None):
    return MemoryStore(
        pool=pool or make_pool(),
        embedder=embedder or make_embedder(),
        openrouter_client=client or AsyncMock(),
        settings=settings or make_settings(),
    )


def make_fact_row(**overrides):
    defaults = {
        "id": uuid4(),
        "key": "name",
        "value": "Alice",
        "agent": "global",
        "confidence": 1.0,
        "reviewed": False,
        "contradicted": False,
        "updated_at": datetime.utcnow(),
    }
    defaults.update(overrides)
    return defaults


def make_episode_row(**overrides):
    defaults = {
        "id": uuid4(),
        "agent": "research",
        "prompt": "what is AI?",
        "response": "AI is artificial intelligence.",
        "summary": None,
        "created_at": datetime.utcnow(),
        "similarity": 0.9,
    }
    defaults.update(overrides)
    return defaults


# ── _vec and _tokens ──────────────────────────────────────────────────────────

def test_vec_formats_numpy_array():
    arr = np.array([0.1, 0.2, 0.3])
    result = _vec(arr)
    assert result.startswith("[")
    assert result.endswith("]")
    assert "0.10000000" in result
    assert result.count(",") == 2


def test_tokens_approximates_length():
    assert _tokens("hello world") == 2  # 11 // 4
    assert _tokens("") == 0
    assert _tokens("a" * 400) == 100


# ── get_context ───────────────────────────────────────────────────────────────

async def test_get_context_returns_memory_context():
    store = make_store()
    ctx = await store.get_context(np.zeros(384), "research")
    assert isinstance(ctx, MemoryContext)
    assert ctx.facts == []
    assert ctx.episodes == []
    assert ctx.token_estimate == 0


async def test_get_context_includes_facts():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [make_fact_row(key="name", value="Alice")],
        [],  # episodes
    ])
    store = make_store(pool=make_pool(conn))
    ctx = await store.get_context(np.zeros(384), "global")
    assert len(ctx.facts) == 1
    assert ctx.facts[0].key == "name"
    assert ctx.facts[0].value == "Alice"


async def test_get_context_token_estimate_is_nonzero_with_content():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [make_fact_row(value="x" * 40)],
        [],
    ])
    store = make_store(pool=make_pool(conn))
    ctx = await store.get_context(np.zeros(384), "global")
    assert ctx.token_estimate > 0


# ── write_episode ─────────────────────────────────────────────────────────────

async def test_write_episode_inserts_row():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))
    await store.write_episode("research", "hello", "world", np.zeros(384))
    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO episodes" in sql


async def test_write_episode_passes_vector_string():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))
    embedding = np.array([0.5] * 384)
    await store.write_episode("research", "p", "r", embedding)
    args = conn.execute.call_args[0]
    vec_arg = args[4]  # $4 is the vector
    assert vec_arg.startswith("[")
    assert "0.50000000" in vec_arg


async def test_write_episode_swallows_db_error():
    conn = make_conn()
    conn.execute = AsyncMock(side_effect=Exception("connection lost"))
    store = make_store(pool=make_pool(conn))
    await store.write_episode("research", "prompt", "response", np.zeros(384))
    # No exception raised


# ── propose_facts ─────────────────────────────────────────────────────────────

async def test_propose_facts_noop_when_empty():
    conn = make_conn()
    store = make_store(pool=make_pool(conn))
    await store.propose_facts([])
    conn.execute.assert_not_awaited()


async def test_propose_facts_inserts_each_fact():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    store = make_store(pool=make_pool(conn))
    facts = [
        UserFact(key="name", value="Alice", agent="companion"),
        UserFact(key="city", value="Lisbon", agent="companion"),
    ]
    await store.propose_facts(facts)
    # One INSERT per fact, no contradictions
    assert conn.execute.await_count == 2


async def test_propose_facts_marks_exact_key_contradicted():
    existing_id = uuid4()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": existing_id})
    conn.fetch = AsyncMock(return_value=[])
    store = make_store(pool=make_pool(conn))
    await store.propose_facts([UserFact(key="name", value="Bob")])
    # execute called twice: UPDATE contradicted + INSERT new
    assert conn.execute.await_count == 2
    first_sql = conn.execute.call_args_list[0][0][0]
    assert "UPDATE" in first_sql
    assert "contradicted" in first_sql


async def test_propose_facts_marks_semantic_duplicate_contradicted():
    other_id = uuid4()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[
        {"id": other_id, "key": "full_name", "value": "Alice Smith"},
    ])
    # Make embedder return identical vectors → similarity = 1.0 > threshold
    embedder = make_embedder()
    embedder.encode = MagicMock(return_value=np.ones(384) / np.linalg.norm(np.ones(384)))
    store = make_store(pool=make_pool(conn), embedder=embedder)
    await store.propose_facts([UserFact(key="name", value="Alice")])
    # UPDATE semantically similar + INSERT new = 2 execute calls
    assert conn.execute.await_count == 2


# ── _load_facts ───────────────────────────────────────────────────────────────

async def test_load_facts_respects_token_budget():
    rows = [make_fact_row(key=f"k{i}", value="x" * 40) for i in range(3)]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)
    store = make_store(pool=make_pool(conn))
    # Each value = 40 chars = 10 tokens; budget 15 → only first fits
    facts = await store._load_facts("global", token_budget=15)
    assert len(facts) == 1


async def test_load_facts_returns_empty_when_no_rows():
    store = make_store()
    facts = await store._load_facts("research", token_budget=200)
    assert facts == []


# ── _load_episodes ────────────────────────────────────────────────────────────

async def test_load_episodes_returns_empty_when_no_rows():
    store = make_store()
    episodes = await store._load_episodes(np.zeros(384), token_budget=500)
    assert episodes == []


async def test_load_episodes_uses_existing_summary():
    row = make_episode_row(summary="A greeting exchange.")
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[row])
    client = AsyncMock()
    store = make_store(pool=make_pool(conn), client=client)
    episodes = await store._load_episodes(np.zeros(384), token_budget=500)
    assert len(episodes) == 1
    assert episodes[0].summary == "A greeting exchange."
    client.complete.assert_not_awaited()


async def test_load_episodes_generates_missing_summary():
    row = make_episode_row(summary=None)
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[row])
    conn.execute = AsyncMock()
    client = AsyncMock()
    client.complete = AsyncMock(return_value="Short AI summary.")
    store = make_store(pool=make_pool(conn), client=client)
    episodes = await store._load_episodes(np.zeros(384), token_budget=500)
    assert len(episodes) == 1
    assert episodes[0].summary == "Short AI summary."
    client.complete.assert_awaited_once()


async def test_load_episodes_persists_generated_summary():
    row = make_episode_row(summary=None)
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[row])
    conn.execute = AsyncMock()
    client = AsyncMock()
    client.complete = AsyncMock(return_value="Cached summary.")
    store = make_store(pool=make_pool(conn), client=client)
    await store._load_episodes(np.zeros(384), token_budget=500)
    # execute called with UPDATE episodes SET summary
    sql = conn.execute.call_args[0][0]
    assert "UPDATE episodes SET summary" in sql


async def test_load_episodes_respects_token_budget():
    rows = [make_episode_row(summary="x" * 40) for _ in range(3)]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)
    store = make_store(pool=make_pool(conn))
    # Each summary = 40 chars = 10 tokens; budget 15 → only first fits
    episodes = await store._load_episodes(np.zeros(384), token_budget=15)
    assert len(episodes) == 1


# ── _generate_summary ─────────────────────────────────────────────────────────

async def test_generate_summary_returns_string():
    client = AsyncMock()
    client.complete = AsyncMock(return_value="short summary")
    store = make_store(client=client)
    result = await store._generate_summary(uuid4(), "prompt text", "response text")
    assert result == "short summary"
    client.complete.assert_awaited_once()


async def test_generate_summary_returns_none_on_error():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("API error"))
    store = make_store(client=client)
    result = await store._generate_summary(uuid4(), "prompt", "response")
    assert result is None
