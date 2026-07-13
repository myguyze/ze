"""Tests for Phase 55 signal substrate: ingest_signal, entity resolution, graph traversal."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


from ze_memory.graph.predicates import MENTIONS
from ze_memory.graph.store import PostgresGraphStore
from ze_memory.retriever import PostgresMemoryStore
from ze_memory.types import EntityRef, Signal, SignalIngestResult


# ── helpers ───────────────────────────────────────────────────────────────────


class _async_ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_):
        pass


def _make_conn(**kwargs) -> AsyncMock:
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
    conn.fetch = AsyncMock(return_value=[])
    conn.execute = AsyncMock()
    for k, v in kwargs.items():
        setattr(conn, k, v)
    return conn


def _make_pool(conn=None):
    if conn is None:
        conn = _make_conn()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_async_ctx(conn))
    return pool, conn


def _make_graph_store() -> MagicMock:
    gs = MagicMock()
    gs.upsert_relationship = AsyncMock(return_value=uuid4())
    return gs


def _make_store(conn=None, graph_store=None) -> tuple[PostgresMemoryStore, AsyncMock]:
    pool, conn = _make_pool(conn)
    store = PostgresMemoryStore.__new__(PostgresMemoryStore)
    store._pool = pool
    store._embedder = None
    store._client = None
    store._graph_store = graph_store
    store._traversal = None
    store._settings = None
    return store, conn


def _make_signal(entities=None, **kwargs) -> Signal:
    return Signal(
        id=uuid4(),
        source="news",
        external_ref="https://example.com/article/1",
        title="Anthropic releases new model",
        summary="Anthropic has released a new AI model.",
        occurred_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        entities=entities or [],
        **kwargs,
    )


# ── ingest_signal: basic write path ──────────────────────────────────────────


async def test_ingest_signal_inserts_row_and_returns_created_true():
    signal_id = uuid4()
    conn = _make_conn()
    # duplicate check → None (new); insert → signal_id
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}])
    store, _ = _make_store(conn)

    result = await store.ingest_signal(_make_signal())

    assert isinstance(result, SignalIngestResult)
    assert result.signal_id == signal_id
    assert result.created is True


async def test_ingest_signal_writes_to_memory_signals_table():
    signal_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}])
    store, _ = _make_store(conn)

    await store.ingest_signal(_make_signal())

    insert_call = conn.fetchrow.call_args_list[1]
    sql = insert_call[0][0]
    assert "memory_signals" in sql
    assert "RETURNING id" in sql


async def test_ingest_signal_expires_at_is_none_on_ingest():
    signal_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}])
    store, _ = _make_store(conn)

    signal = _make_signal()
    assert signal.expires_at is None

    result = await store.ingest_signal(signal)
    assert result is not None

    insert_call = conn.fetchrow.call_args_list[1]
    args = insert_call[0]
    # expires_at is the 9th positional arg (index 8)
    assert args[9] is None  # expires_at


# ── ingest_signal: deduplication ─────────────────────────────────────────────


async def test_ingest_signal_dedupes_on_source_and_external_ref():
    existing_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": existing_id})  # duplicate found
    store, _ = _make_store(conn)

    result = await store.ingest_signal(_make_signal())

    assert result is not None
    assert result.signal_id == existing_id
    assert result.created is False
    assert result.entity_ids == []


async def test_ingest_signal_deduped_does_not_insert():
    existing_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": existing_id})
    store, _ = _make_store(conn)

    await store.ingest_signal(_make_signal())

    # Only the duplicate-check SELECT was called — no INSERT
    assert conn.fetchrow.call_count == 1
    sql = conn.fetchrow.call_args[0][0]
    assert "SELECT" in sql or "FROM memory_signals" in sql


# ── ingest_signal: entity resolution and MENTIONS edges ──────────────────────


async def test_ingest_signal_creates_mentions_edges_for_each_entity():
    signal_id = uuid4()
    entity_id = uuid4()
    conn = _make_conn()
    # duplicate check → None; insert signal → signal_id; upsert_entity → entity_id
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}, {"id": entity_id}])
    gs = _make_graph_store()
    store, _ = _make_store(conn, graph_store=gs)

    signal = _make_signal(entities=[EntityRef(name="Anthropic", entity_type="org")])
    result = await store.ingest_signal(signal)

    assert result is not None
    assert result.entity_ids == [entity_id]
    gs.upsert_relationship.assert_awaited_once()
    rel = gs.upsert_relationship.call_args[0][0]
    assert rel.predicate == MENTIONS
    assert rel.source_id == signal_id
    assert rel.source_type == "signal"
    assert rel.target_id == entity_id
    assert rel.target_type == "entity"


async def test_ingest_signal_creates_mentions_edge_for_topic_entity():
    signal_id = uuid4()
    topic_entity_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(
        side_effect=[None, {"id": signal_id}, {"id": topic_entity_id}]
    )
    gs = _make_graph_store()
    store, _ = _make_store(conn, graph_store=gs)

    signal = _make_signal(
        entities=[EntityRef(name="artificial-intelligence", entity_type="topic")]
    )
    result = await store.ingest_signal(signal)

    assert result is not None
    assert topic_entity_id in result.entity_ids
    rel = gs.upsert_relationship.call_args[0][0]
    assert rel.target_id == topic_entity_id


async def test_ingest_signal_multiple_entities_produces_multiple_edges():
    signal_id = uuid4()
    entity1_id = uuid4()
    entity2_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(
        side_effect=[None, {"id": signal_id}, {"id": entity1_id}, {"id": entity2_id}]
    )
    gs = _make_graph_store()
    store, _ = _make_store(conn, graph_store=gs)

    signal = _make_signal(
        entities=[
            EntityRef(name="Anthropic", entity_type="org"),
            EntityRef(name="machine-learning", entity_type="topic"),
        ]
    )
    result = await store.ingest_signal(signal)

    assert result is not None
    assert len(result.entity_ids) == 2
    assert gs.upsert_relationship.await_count == 2
    predicates = [c[0][0].predicate for c in gs.upsert_relationship.call_args_list]
    assert all(p == MENTIONS for p in predicates)


async def test_ingest_signal_no_entities_writes_node_with_no_edges():
    signal_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}])
    gs = _make_graph_store()
    store, _ = _make_store(conn, graph_store=gs)

    result = await store.ingest_signal(_make_signal(entities=[]))

    assert result is not None
    assert result.created is True
    assert result.entity_ids == []
    gs.upsert_relationship.assert_not_awaited()


async def test_ingest_signal_no_graph_store_still_inserts_node():
    signal_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=[None, {"id": signal_id}])
    store, _ = _make_store(conn, graph_store=None)

    signal = _make_signal(entities=[EntityRef(name="Anthropic", entity_type="org")])
    result = await store.ingest_signal(signal)

    assert result is not None
    assert result.signal_id == signal_id
    assert result.created is True


async def test_ingest_signal_swallows_db_error():
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("DB down"))
    store, _ = _make_store(conn)

    result = await store.ingest_signal(_make_signal())
    assert result is None


# ── entity resolution: non-person types ──────────────────────────────────────


async def test_resolve_entity_ref_creates_org_entity():
    org_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": org_id})
    store, _ = _make_store(conn)

    existing: dict = {}
    result = await store._resolve_entity_ref(
        EntityRef(name="OpenAI", entity_type="org"), existing
    )

    assert result == org_id
    assert existing["openai"] == org_id
    insert_args = conn.fetchrow.call_args[0]
    assert "org" in insert_args


async def test_resolve_entity_ref_creates_topic_entity():
    topic_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": topic_id})
    store, _ = _make_store(conn)

    existing: dict = {}
    result = await store._resolve_entity_ref(
        EntityRef(name="machine-learning", entity_type="topic"), existing
    )

    assert result == topic_id
    insert_args = conn.fetchrow.call_args[0]
    assert "topic" in insert_args


async def test_resolve_entity_ref_creates_ticker_entity():
    ticker_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": ticker_id})
    store, _ = _make_store(conn)

    existing: dict = {}
    result = await store._resolve_entity_ref(
        EntityRef(name="NVDA", entity_type="ticker"), existing
    )

    assert result == ticker_id
    insert_args = conn.fetchrow.call_args[0]
    assert "ticker" in insert_args


async def test_resolve_entity_ref_uses_cache_on_second_call():
    entity_id = uuid4()
    conn = _make_conn()
    conn.fetchrow = AsyncMock(return_value={"id": entity_id})
    store, _ = _make_store(conn)

    existing: dict = {}
    first = await store._resolve_entity_ref(
        EntityRef(name="Anthropic", entity_type="org"), existing
    )
    second = await store._resolve_entity_ref(
        EntityRef(name="Anthropic", entity_type="org"), existing
    )

    assert first == second == entity_id
    # DB only called once — second call hits the cache
    assert conn.fetchrow.call_count == 1


async def test_resolve_entity_ref_returns_none_for_empty_name():
    conn = _make_conn()
    store, _ = _make_store(conn)
    existing: dict = {}
    result = await store._resolve_entity_ref(
        EntityRef(name="", entity_type="topic"), existing
    )
    assert result is None
    conn.fetchrow.assert_not_awaited()


async def test_resolve_entity_ref_returns_none_on_db_error():
    conn = _make_conn()
    conn.fetchrow = AsyncMock(side_effect=RuntimeError("constraint"))
    store, _ = _make_store(conn)
    existing: dict = {}
    result = await store._resolve_entity_ref(
        EntityRef(name="BadCo", entity_type="org"), existing
    )
    assert result is None


async def test_resolve_participant_names_delegates_to_entity_ref_as_person():
    """_resolve_participant_names still works correctly after refactor."""
    entity_id = uuid4()
    conn = _make_conn()
    conn.fetch = AsyncMock(return_value=[])  # no existing match → will create
    conn.fetchrow = AsyncMock(return_value={"id": entity_id})
    store, _ = _make_store(conn)

    result = await store._resolve_participant_names(["Alice"])

    assert result == [entity_id]
    insert_args = conn.fetchrow.call_args[0]
    assert "person" in insert_args


# ── graph traversal: signal_ids bucketed correctly ────────────────────────────


class TestExpandSignalBucketing:
    def _make_row(self, source_id, target_id, target_type, predicate=MENTIONS):
        return {
            "id": uuid4(),
            "source_id": source_id,
            "source_type": "entity",
            "predicate": predicate,
            "target_id": target_id,
            "target_type": target_type,
            "target_text": None,
            "confidence": 0.9,
            "provenance_id": None,
            "creation_method": "extracted",
            "reviewed": False,
            "created_at": None,
            "updated_at": None,
        }

    @asynccontextmanager
    async def _pool_with_rows(self, rows):
        conn = AsyncMock()
        conn.fetch = AsyncMock(return_value=rows)

        @asynccontextmanager
        async def _acquire():
            yield conn

        pool = MagicMock()
        pool.acquire = _acquire
        yield pool

    async def test_expand_buckets_signal_target_into_signal_ids(self):
        """expand() places target_type='signal' nodes into GraphExpansion.signal_ids."""
        entity_id = uuid4()
        signal_id = uuid4()
        rows = [self._make_row(entity_id, signal_id, "signal")]

        async with self._pool_with_rows(rows) as pool:
            store = PostgresGraphStore(pool=pool)
            expansion = await store.expand([entity_id])

        assert signal_id in expansion.signal_ids
        assert len(expansion.relationships) == 1

    async def test_expand_cross_domain_entity_to_signal_and_episode(self):
        """expand() from an entity reaches both a signal and an episode that mention it."""
        entity_id = uuid4()
        signal_id = uuid4()
        episode_id = uuid4()
        rows = [
            self._make_row(entity_id, signal_id, "signal"),
            self._make_row(entity_id, episode_id, "episode"),
        ]

        async with self._pool_with_rows(rows) as pool:
            store = PostgresGraphStore(pool=pool)
            expansion = await store.expand([entity_id])

        assert signal_id in expansion.signal_ids
        assert episode_id in expansion.episode_ids
        assert len(expansion.relationships) == 2

    async def test_expand_topic_entity_links_signal_and_episode(self):
        """expand() via a shared Topic entity reaches both a signal and an episode."""
        topic_entity_id = uuid4()
        signal_id = uuid4()
        episode_id = uuid4()
        rows = [
            self._make_row(topic_entity_id, signal_id, "signal"),
            self._make_row(topic_entity_id, episode_id, "episode"),
        ]

        async with self._pool_with_rows(rows) as pool:
            store = PostgresGraphStore(pool=pool)
            expansion = await store.expand([topic_entity_id])

        assert signal_id in expansion.signal_ids
        assert episode_id in expansion.episode_ids

    async def test_expand_signal_not_mixed_with_other_buckets(self):
        """signal_ids must not bleed into fact_ids, entity_ids, or episode_ids."""
        entity_id = uuid4()
        signal_id = uuid4()
        fact_id = uuid4()
        rows = [
            self._make_row(entity_id, signal_id, "signal"),
            self._make_row(entity_id, fact_id, "fact"),
        ]

        async with self._pool_with_rows(rows) as pool:
            store = PostgresGraphStore(pool=pool)
            expansion = await store.expand([entity_id])

        assert signal_id in expansion.signal_ids
        assert fact_id in expansion.fact_ids
        assert signal_id not in expansion.fact_ids
        assert fact_id not in expansion.signal_ids
