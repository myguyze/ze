"""Tests for the relevance floor (User Story 1): real similarity scores + FR-002/FR-017."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from ze_agents.types import RetrievalRequest
from ze_memory.policies import CompanionPolicy, ResearchPolicy, apply_relevance_floor
from ze_memory.projection import _entity_from_row, _event_from_row, _fact_from_row
from ze_memory.relevance_config import RelevanceConfig


def _fact_row(similarity, **overrides):
    row = {
        "id": uuid4(),
        "subject_id": None,
        "predicate": "likes",
        "object_text": None,
        "object_id": None,
        "value": "the user likes coffee",
        "confidence": 0.9,
        "reviewed": False,
        "contradicted": False,
        "source_episode_id": None,
        "source_refs": "[]",
        "provenance": "raw",
        "similarity": similarity,
    }
    row.update(overrides)
    return row


def _episode_row(similarity, **overrides):
    row = {
        "id": uuid4(),
        "session_id": "sess-other",
        "agent": "companion",
        "prompt": "hi",
        "response": "hello there",
        "summary": "greeting",
        "relevance": 0.5,
        "created_at": None,
        "linked_entity_ids": "[]",
        "linked_fact_ids": "[]",
        "similarity": similarity,
    }
    row.update(overrides)
    return row


# ── T008: SQL similarity column correctly mapped to relevance_score ───────────


def test_fact_from_row_maps_similarity_to_relevance_score():
    fact = _fact_from_row(_fact_row(0.82))
    assert fact.relevance_score == 0.82


def test_fact_from_row_relevance_score_none_when_similarity_absent():
    row = _fact_row(None)
    fact = _fact_from_row(row)
    assert fact.relevance_score is None


def test_entity_from_row_maps_similarity_to_relevance_score():
    row = {
        "id": uuid4(),
        "entity_type": "person",
        "canonical_name": "Ada",
        "aliases": "[]",
        "attrs": "{}",
        "similarity": 0.71,
    }
    entity = _entity_from_row(row)
    assert entity.relevance_score == 0.71


def test_event_from_row_maps_similarity_to_relevance_score():
    row = {
        "id": uuid4(),
        "event_type": "meeting",
        "title": "Standup",
        "similarity": 0.44,
    }
    event = _event_from_row(row)
    assert event.relevance_score == 0.44


# ── T009: candidates below floor (incl. per-type override) are excluded ───────


def test_apply_relevance_floor_drops_rows_below_global_floor():
    cfg = RelevanceConfig(floor=0.35, floor_overrides={})
    rows = [_fact_row(0.9), _fact_row(0.2), _fact_row(0.35)]
    kept = apply_relevance_floor(rows, "fact", cfg)
    assert [r["similarity"] for r in kept] == [0.9, 0.35]


def test_apply_relevance_floor_applies_per_type_override():
    cfg = RelevanceConfig(floor=0.35, floor_overrides={"episode": 0.6})
    rows = [_episode_row(0.5), _episode_row(0.7)]
    kept = apply_relevance_floor(rows, "episode", cfg)
    assert [r["similarity"] for r in kept] == [0.7]


def test_apply_relevance_floor_drops_null_similarity_when_floor_active():
    cfg = RelevanceConfig(floor=0.35)
    rows = [_fact_row(None), _fact_row(0.9)]
    kept = apply_relevance_floor(rows, "fact", cfg)
    assert [r["similarity"] for r in kept] == [0.9]


# ── T010: relevance_floor = 0 reproduces pre-phase-106 ordering (FR-017) ──────


def test_apply_relevance_floor_zero_keeps_everything_including_null():
    cfg = RelevanceConfig(floor=0)
    rows = [_fact_row(0.9), _fact_row(0.01), _fact_row(None)]
    kept = apply_relevance_floor(rows, "fact", cfg)
    assert kept == rows


# ── T009 continued: end-to-end floor exclusion via CompanionPolicy/ResearchPolicy


def _async_ctx(conn):
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx


def _make_store(conn, *, settings=None):
    store = MagicMock()
    store.pool = MagicMock()
    store.pool.acquire = MagicMock(return_value=_async_ctx(conn))
    store.settings = settings if settings is not None else {"memory": {"relevance_floor": 0.35}}
    store.get_task_state = AsyncMock(return_value=None)
    return store


def _request(**overrides):
    defaults = dict(
        module="companion",
        agent="companion",
        query_text="what does the user like",
        query_embedding=[0.1, 0.2, 0.3],
        current_session_id="sess-current",
    )
    defaults.update(overrides)
    return RetrievalRequest(**defaults)


@patch("ze_memory.policies._fetch_session_summary_rows", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_events_by_similarity", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_entities_by_similarity", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_facts_by_similarity", new_callable=AsyncMock)
async def test_companion_policy_excludes_low_similarity_facts(
    mock_facts, mock_entities, mock_events, mock_summaries
):
    mock_facts.return_value = [_fact_row(0.9), _fact_row(0.1)]
    mock_entities.return_value = []
    mock_events.return_value = []
    mock_summaries.return_value = []

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[[], []])  # episode_rows, profile_rows
    store = _make_store(conn)

    ctx = await CompanionPolicy().retrieve(_request(), store)

    assert len(ctx.facts) == 1
    assert ctx.facts[0].relevance_score == 0.9


@patch("ze_memory.policies._fetch_session_summary_rows", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_events_by_similarity", new_callable=AsyncMock)
async def test_research_policy_excludes_low_similarity_episodes(
    mock_events, mock_summaries
):
    mock_events.return_value = []
    mock_summaries.return_value = []

    conn = AsyncMock()
    conn.fetch = AsyncMock(
        side_effect=[
            [_fact_row(0.9)],  # fact_rows (inline query)
            [_episode_row(0.9), _episode_row(0.1)],  # episode_rows
        ]
    )
    store = _make_store(conn)

    ctx = await ResearchPolicy().retrieve(_request(module="research", agent="research"), store)

    assert len(ctx.episodes) == 1
    assert ctx.episodes[0].relevance_score == 0.9


@patch("ze_memory.policies._fetch_session_summary_rows", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_events_by_similarity", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_entities_by_similarity", new_callable=AsyncMock)
@patch("ze_memory.policies._fetch_facts_by_similarity", new_callable=AsyncMock)
async def test_companion_policy_floor_zero_reproduces_pre_phase_106_ordering(
    mock_facts, mock_entities, mock_events, mock_summaries
):
    mock_facts.return_value = [_fact_row(0.9), _fact_row(0.01), _fact_row(None)]
    mock_entities.return_value = []
    mock_events.return_value = []
    mock_summaries.return_value = []

    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=[[], []])
    store = _make_store(conn, settings={"memory": {"relevance_floor": 0}})

    ctx = await CompanionPolicy().retrieve(_request(), store)

    assert len(ctx.facts) == 3
