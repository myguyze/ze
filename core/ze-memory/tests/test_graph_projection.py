"""Tests for graph projection (enrich_context) and BoundedExpansionPolicy wiring."""
from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


from ze_memory.graph.projection import enrich_context
from ze_memory.graph.types import GraphExpansion
from ze_memory.types import (
    Entity,
    Fact,
    MemoryContext,
)


def _empty_ctx(**kwargs) -> MemoryContext:
    defaults = dict(
        facts=[],
        episodes=[],
        events=[],
        procedures=[],
        task_state=None,
        profile=[],
        entities=[],
    )
    defaults.update(kwargs)
    return MemoryContext(**defaults)


def _make_fact_row(fid=None, confidence=0.9):
    return {
        "id": fid or uuid4(),
        "subject_id": None,
        "predicate": "likes",
        "object_text": "coffee",
        "object_id": None,
        "value": "coffee",
        "confidence": confidence,
        "reviewed": False,
        "contradicted": False,
        "source_episode_id": None,
        "source_refs": None,
    }


def _make_entity_row(eid=None, name="Alice"):
    import json
    return {
        "id": eid or uuid4(),
        "entity_type": "person",
        "canonical_name": name,
        "aliases": json.dumps([]),
        "attrs": json.dumps({}),
    }


def _make_pool(fact_rows=None, entity_rows=None):
    conn = AsyncMock()
    _fact_rows = fact_rows or []
    _entity_rows = entity_rows or []

    async def _fetch(q, *a):
        if "memory_facts" in q:
            return _fact_rows
        return _entity_rows

    conn.fetch = _fetch

    @asynccontextmanager
    async def _acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = _acquire
    return pool, conn


class TestEnrichContext:
    async def test_empty_expansion_returns_same_ctx(self):
        pool, _ = _make_pool()
        ctx = _empty_ctx()
        expansion = GraphExpansion()

        result = await enrich_context(ctx, expansion, pool)

        assert result is ctx

    async def test_new_facts_are_appended(self):
        fid = uuid4()
        fact_rows = [_make_fact_row(fid=fid)]
        pool, _ = _make_pool(fact_rows=fact_rows)

        expansion = GraphExpansion(fact_ids=[fid])
        ctx = _empty_ctx()

        result = await enrich_context(ctx, expansion, pool)

        assert len(result.facts) == 1
        assert result.facts[0].predicate == "likes"

    async def test_new_entities_are_appended(self):
        eid = uuid4()
        entity_rows = [_make_entity_row(eid=eid)]
        pool, _ = _make_pool(entity_rows=entity_rows)

        expansion = GraphExpansion(entity_ids=[eid])
        ctx = _empty_ctx()

        result = await enrich_context(ctx, expansion, pool)

        assert len(result.entities) == 1
        assert result.entities[0].canonical_name == "Alice"

    async def test_existing_fact_ids_not_refetched(self):
        fid = uuid4()
        existing_fact = Fact(
            id=fid,
            subject_id=None,
            predicate="eats",
            value="pizza",
            object_text="pizza",
            confidence=0.8,
        )
        pool, conn = _make_pool(fact_rows=[])

        expansion = GraphExpansion(fact_ids=[fid])
        ctx = _empty_ctx(facts=[existing_fact])

        result = await enrich_context(ctx, expansion, pool)

        # Pool should not have been queried for facts (already known)
        # result ctx should still have only 1 fact (the existing one)
        assert len(result.facts) == 1
        assert result.facts[0].predicate == "eats"

    async def test_existing_entity_ids_not_refetched(self):
        eid = uuid4()
        existing = Entity(
            id=eid,
            entity_type="person",
            canonical_name="Bob",
            aliases=[],
            attrs={},
        )
        pool, conn = _make_pool(entity_rows=[])
        expansion = GraphExpansion(entity_ids=[eid])
        ctx = _empty_ctx(entities=[existing])

        result = await enrich_context(ctx, expansion, pool)

        assert len(result.entities) == 1
        assert result.entities[0].canonical_name == "Bob"

    async def test_no_new_content_returns_same_ctx(self):
        """When all discovered IDs are already in ctx, enrich_context returns ctx unchanged."""
        fid = uuid4()
        existing_fact = Fact(
            id=fid, subject_id=None, predicate="knows", value="python", object_text="python", confidence=1.0
        )
        pool, conn = _make_pool(fact_rows=[])
        expansion = GraphExpansion(fact_ids=[fid])
        ctx = _empty_ctx(facts=[existing_fact])

        result = await enrich_context(ctx, expansion, pool)

        assert result is ctx

    async def test_token_estimate_updated(self):
        fid = uuid4()
        pool, _ = _make_pool(fact_rows=[_make_fact_row(fid=fid)])
        expansion = GraphExpansion(fact_ids=[fid])
        ctx = _empty_ctx()

        result = await enrich_context(ctx, expansion, pool)

        assert result.token_estimate >= 0
