"""Tests for entity-anchored retrieval (User Story 2, phase 106)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_memory.entity_anchor import (
    EntityAnchorMatch,
    augment_with_entity_anchor,
    fetch_anchored_candidates,
    match_entities_in_query,
    merge_candidates,
)
from ze_memory.graph.types import GraphExpansion
from ze_memory.relevance_config import RelevanceConfig
from ze_memory.types import Fact, MemoryContext


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _entity_row(entity_id, canonical_name, aliases=None):
    return {
        "id": entity_id,
        "entity_type": "person",
        "canonical_name": canonical_name,
        "aliases": aliases or [],
        "attrs": {},
    }


# ── T023: match_entities_in_query is word-bounded, case-insensitive, canonical wins ─


async def test_match_entities_in_query_is_word_bounded():
    entity_id = uuid4()
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_entity_row(entity_id, "Al")])
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    matches = await match_entities_in_query("Sally went home", pool)
    assert matches == []

    matches = await match_entities_in_query("Al went home", pool)
    assert len(matches) == 1
    assert matches[0].entity.id == entity_id


async def test_match_entities_in_query_is_case_insensitive():
    entity_id = uuid4()
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[_entity_row(entity_id, "Ada Lovelace")])
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    matches = await match_entities_in_query("tell me about ADA LOVELACE please", pool)
    assert len(matches) == 1
    assert matches[0].match_kind == "canonical_name"


async def test_match_entities_in_query_prefers_canonical_over_alias():
    entity_id = uuid4()
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[_entity_row(entity_id, "Robert", aliases=["Bob"])]
    )
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    matches = await match_entities_in_query("Robert and Bob are the same person", pool)
    assert len(matches) == 1
    assert matches[0].match_kind == "canonical_name"
    assert matches[0].matched_text == "Robert"


async def test_match_entities_in_query_matches_alias_when_no_canonical_hit():
    entity_id = uuid4()
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[_entity_row(entity_id, "Robert", aliases=["Bob"])]
    )
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    matches = await match_entities_in_query("what does Bob like", pool)
    assert len(matches) == 1
    assert matches[0].match_kind == "alias"
    assert matches[0].matched_text == "Bob"


async def test_match_entities_in_query_returns_empty_on_db_error():
    pool = MagicMock()
    pool.acquire = MagicMock(side_effect=RuntimeError("db down"))
    matches = await match_entities_in_query("anything", pool)
    assert matches == []


async def test_match_entities_in_query_empty_text_short_circuits():
    pool = MagicMock()
    matches = await match_entities_in_query("   ", pool)
    assert matches == []


# ── T024: fetch_anchored_candidates — one-hop neighbours + validity filters ───


async def test_fetch_anchored_candidates_returns_one_hop_facts():
    entity_id = uuid4()
    fact_id = uuid4()
    match = EntityAnchorMatch(
        entity=MagicMock(id=entity_id), matched_text="Ada", match_kind="canonical_name"
    )

    expansion = GraphExpansion(fact_ids=[fact_id])
    graph_store = AsyncMock()
    graph_store.expand = AsyncMock(return_value=expansion)

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        return_value=[
            {
                "id": fact_id,
                "subject_id": entity_id,
                "predicate": "likes",
                "object_text": None,
                "object_id": None,
                "value": "the user likes tea",
                "confidence": 0.8,
                "reviewed": False,
                "contradicted": False,
                "source_episode_id": None,
                "source_refs": "[]",
                "provenance": "raw",
            }
        ]
    )
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    cfg = RelevanceConfig(entity_match_constant=0.75)
    ctx = await fetch_anchored_candidates([match], graph_store, pool, cfg)

    assert len(ctx.facts) == 1
    assert ctx.facts[0].relevance_score == 0.75
    assert ctx.facts[0].retrieval_provenance == "entity_anchor"
    graph_store.expand.assert_awaited_once_with([entity_id], max_hops=1)


async def test_fetch_anchored_candidates_empty_when_no_matches():
    ctx = await fetch_anchored_candidates([], AsyncMock(), MagicMock(), RelevanceConfig())
    assert ctx.facts == []
    assert ctx.episodes == []


async def test_fetch_anchored_candidates_degrades_on_expand_failure():
    match = EntityAnchorMatch(
        entity=MagicMock(id=uuid4()), matched_text="Ada", match_kind="canonical_name"
    )
    graph_store = AsyncMock()
    graph_store.expand = AsyncMock(side_effect=RuntimeError("graph down"))

    ctx = await fetch_anchored_candidates(
        [match], graph_store, MagicMock(), RelevanceConfig()
    )
    assert ctx.facts == []


# ── T025: score = max(vector_similarity, entity_match_constant); dedup keeps strongest


def test_merge_candidates_keeps_max_relevance_score_on_overlap():
    shared_id = uuid4()
    vector_ctx = MemoryContext(
        facts=[Fact(id=shared_id, predicate="p", value="v", relevance_score=0.4)]
    )
    anchor_ctx = MemoryContext(
        facts=[
            Fact(
                id=shared_id,
                predicate="p",
                value="v",
                relevance_score=0.75,
                retrieval_provenance="entity_anchor",
            )
        ]
    )
    merged = merge_candidates(vector_ctx, anchor_ctx)
    assert len(merged.facts) == 1
    assert merged.facts[0].relevance_score == 0.75


def test_merge_candidates_keeps_vector_score_when_higher():
    shared_id = uuid4()
    vector_ctx = MemoryContext(
        facts=[Fact(id=shared_id, predicate="p", value="v", relevance_score=0.9)]
    )
    anchor_ctx = MemoryContext(
        facts=[
            Fact(
                id=shared_id,
                predicate="p",
                value="v",
                relevance_score=0.75,
                retrieval_provenance="entity_anchor",
            )
        ]
    )
    merged = merge_candidates(vector_ctx, anchor_ctx)
    assert merged.facts[0].relevance_score == 0.9


def test_merge_candidates_keeps_both_when_distinct_ids():
    vector_ctx = MemoryContext(
        facts=[Fact(id=uuid4(), predicate="a", value="1", relevance_score=0.5)]
    )
    anchor_ctx = MemoryContext(
        facts=[Fact(id=uuid4(), predicate="b", value="2", relevance_score=0.75)]
    )
    merged = merge_candidates(vector_ctx, anchor_ctx)
    assert len(merged.facts) == 2


# ── T026: query mentioning no known entity behaves identically to vector-only ─


async def test_augment_with_entity_anchor_returns_ctx_unchanged_when_no_matches():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])  # no entities in DB
    pool.acquire = MagicMock(return_value=_async_ctx(conn))

    original = MemoryContext(facts=[Fact(id=uuid4(), predicate="p", value="v")])
    result = await augment_with_entity_anchor(
        original, "no entities mentioned here", pool, AsyncMock(), RelevanceConfig()
    )
    assert result is original


async def test_augment_with_entity_anchor_disabled_by_config():
    original = MemoryContext(facts=[])
    result = await augment_with_entity_anchor(
        original,
        "Ada",
        MagicMock(),
        AsyncMock(),
        RelevanceConfig(entity_anchor_enabled=False),
    )
    assert result is original


async def test_augment_with_entity_anchor_none_graph_store_is_noop():
    original = MemoryContext(facts=[])
    result = await augment_with_entity_anchor(
        original, "Ada", MagicMock(), None, RelevanceConfig()
    )
    assert result is original


async def test_augment_with_entity_anchor_degrades_gracefully_on_exception():
    pool = MagicMock()
    pool.acquire = MagicMock(side_effect=RuntimeError("boom"))
    original = MemoryContext(facts=[])
    result = await augment_with_entity_anchor(
        original, "Ada", pool, AsyncMock(), RelevanceConfig()
    )
    assert result is original
