"""Tests for PostgresGraphStore and BoundedExpansionPolicy."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_memory.graph.predicates import DESCRIBES, MENTIONS, SOURCED_FROM
from ze_memory.graph.store import PostgresGraphStore
from ze_memory.graph.traversal import BoundedExpansionPolicy
from ze_memory.graph.types import GraphExpansion, Relationship


def _make_rel(
    source_id=None,
    predicate=DESCRIBES,
    target_id=None,
    target_type="fact",
    target_text=None,
    confidence=1.0,
):
    return Relationship(
        source_id=source_id or uuid4(),
        source_type="entity",
        predicate=predicate,
        target_id=target_id or uuid4(),
        target_type=target_type,
        target_text=target_text,
        confidence=confidence,
        creation_method="explicit",
    )


def _make_pool(rows_by_query=None):
    """Return a mock asyncpg pool whose fetchrow/fetch return canned data."""
    rows_by_query = rows_by_query or {}
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=lambda q, *a, **kw: AsyncMock(
        return_value={"id": uuid4()}
    )())
    conn.fetch = AsyncMock(return_value=[])

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    return pool, conn


# ── upsert_relationship ───────────────────────────────────────────────────────

class TestUpsertRelationship:
    async def test_returns_id(self):
        pool, conn = _make_pool()
        returned_id = uuid4()
        conn.fetchrow = AsyncMock(return_value={"id": returned_id})

        store = PostgresGraphStore(pool=pool)
        rel = _make_rel()
        result = await store.upsert_relationship(rel)

        assert result == returned_id

    async def test_uses_target_id_branch_when_set(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
        store = PostgresGraphStore(pool=pool)
        rel = _make_rel(target_id=uuid4())

        await store.upsert_relationship(rel)

        sql = conn.fetchrow.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "target_id IS NOT NULL" in sql

    async def test_uses_text_branch_when_no_target_id(self):
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(return_value={"id": uuid4()})
        store = PostgresGraphStore(pool=pool)
        rel = Relationship(
            source_id=uuid4(),
            source_type="entity",
            predicate=DESCRIBES,
            target_id=None,
            target_text="some text",
        )

        await store.upsert_relationship(rel)

        sql = conn.fetchrow.call_args[0][0]
        assert "ON CONFLICT" not in sql


# ── list_relationships ────────────────────────────────────────────────────────

class TestListRelationships:
    def _make_row(self, source_id, target_id, predicate=DESCRIBES):
        return {
            "id": uuid4(),
            "source_id": source_id,
            "source_type": "entity",
            "predicate": predicate,
            "target_id": target_id,
            "target_type": "fact",
            "target_text": None,
            "confidence": 1.0,
            "provenance_id": None,
            "creation_method": "explicit",
            "reviewed": False,
            "created_at": None,
            "updated_at": None,
        }

    async def test_empty_source_ids_returns_empty(self):
        pool, _ = _make_pool()
        store = PostgresGraphStore(pool=pool)
        result = await store.list_relationships([])
        assert result == []

    async def test_returns_relationships(self):
        pool, conn = _make_pool()
        sid = uuid4()
        tid = uuid4()
        conn.fetch = AsyncMock(return_value=[self._make_row(sid, tid)])

        store = PostgresGraphStore(pool=pool)
        rels = await store.list_relationships([sid])

        assert len(rels) == 1
        assert rels[0].source_id == sid
        assert rels[0].target_id == tid

    async def test_filters_by_predicates(self):
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(return_value=[])
        store = PostgresGraphStore(pool=pool)

        await store.list_relationships([uuid4()], predicates=[DESCRIBES])

        sql = conn.fetch.call_args[0][0]
        assert "predicate = ANY($2)" in sql


# ── expand ────────────────────────────────────────────────────────────────────

class TestExpand:
    def _make_row(self, source_id, target_id, target_type="fact", predicate=DESCRIBES):
        return {
            "id": uuid4(),
            "source_id": source_id,
            "source_type": "entity",
            "predicate": predicate,
            "target_id": target_id,
            "target_type": target_type,
            "target_text": None,
            "confidence": 1.0,
            "provenance_id": None,
            "creation_method": "explicit",
            "reviewed": False,
            "created_at": None,
            "updated_at": None,
        }

    async def test_empty_seeds_returns_empty_expansion(self):
        pool, _ = _make_pool()
        store = PostgresGraphStore(pool=pool)
        expansion = await store.expand([])
        assert expansion.is_empty()

    async def test_single_hop_buckets_fact(self):
        pool, conn = _make_pool()
        eid = uuid4()
        fid = uuid4()
        conn.fetch = AsyncMock(return_value=[self._make_row(eid, fid, "fact")])

        store = PostgresGraphStore(pool=pool)
        expansion = await store.expand([eid])

        assert fid in expansion.fact_ids
        assert len(expansion.relationships) == 1

    async def test_single_hop_buckets_entity(self):
        pool, conn = _make_pool()
        seed = uuid4()
        target = uuid4()
        conn.fetch = AsyncMock(return_value=[self._make_row(seed, target, "entity", MENTIONS)])

        store = PostgresGraphStore(pool=pool)
        expansion = await store.expand([seed])

        assert target in expansion.entity_ids

    async def test_limit_caps_relationships(self):
        pool, conn = _make_pool()
        seed = uuid4()
        rows = [self._make_row(seed, uuid4(), "fact") for _ in range(10)]
        conn.fetch = AsyncMock(return_value=rows)

        store = PostgresGraphStore(pool=pool)
        expansion = await store.expand([seed], limit=3)

        assert len(expansion.relationships) == 3

    async def test_visited_ids_not_re_expanded(self):
        """A target discovered in hop 1 is not re-fetched as seed in hop 2 if already visited."""
        pool, conn = _make_pool()
        seed = uuid4()
        target = uuid4()
        conn.fetch = AsyncMock(
            side_effect=[
                [self._make_row(seed, target, "entity", MENTIONS)],
                [],
            ]
        )

        store = PostgresGraphStore(pool=pool)
        # Run 2 hops; target becomes next frontier but fetch returns []
        await store.expand([seed], max_hops=2, limit=20)

        assert conn.fetch.call_count == 2


# ── BoundedExpansionPolicy ────────────────────────────────────────────────────

class TestBoundedExpansionPolicy:
    async def test_delegates_to_store(self):
        store = AsyncMock()
        store.expand = AsyncMock(return_value=GraphExpansion())
        policy = BoundedExpansionPolicy(graph_store=store, max_hops=2, limit=15)

        seed = [uuid4()]
        await policy.expand(seed)

        store.expand.assert_awaited_once_with(seed, max_hops=2, limit=15)

    async def test_empty_seeds_short_circuits(self):
        store = AsyncMock()
        policy = BoundedExpansionPolicy(graph_store=store)
        result = await policy.expand([])
        store.expand.assert_not_awaited()
        assert result.is_empty()


# ── _build_traversal (config-driven construction) ─────────────────────────────

class TestBuildTraversal:
    def _make_gs(self):
        gs = MagicMock()
        gs.upsert_relationship = AsyncMock()
        return gs

    def test_none_graph_store_returns_none(self):
        from ze_memory.retriever import PostgresMemoryStore
        assert PostgresMemoryStore._build_traversal(None, None) is None

    def test_enabled_true_returns_policy(self):
        from ze_memory.retriever import PostgresMemoryStore
        settings = {"memory": {"graph": {"enabled": True, "max_hops": 2, "max_relationships": 15}}}
        result = PostgresMemoryStore._build_traversal(self._make_gs(), settings)
        assert isinstance(result, BoundedExpansionPolicy)
        assert result._max_hops == 2
        assert result._limit == 15

    def test_enabled_false_returns_none(self):
        from ze_memory.retriever import PostgresMemoryStore
        settings = {"memory": {"graph": {"enabled": False}}}
        result = PostgresMemoryStore._build_traversal(self._make_gs(), settings)
        assert result is None

    def test_defaults_when_no_config(self):
        from ze_memory.retriever import PostgresMemoryStore
        result = PostgresMemoryStore._build_traversal(self._make_gs(), None)
        assert isinstance(result, BoundedExpansionPolicy)
        assert result._max_hops == 1
        assert result._limit == 20

    def test_reads_from_settings_object_with_config_attr(self):
        from ze_memory.retriever import PostgresMemoryStore
        settings = MagicMock()
        settings.config = {"memory": {"graph": {"enabled": True, "max_hops": 3, "max_relationships": 10}}}
        result = PostgresMemoryStore._build_traversal(self._make_gs(), settings)
        assert result._max_hops == 3
        assert result._limit == 10
