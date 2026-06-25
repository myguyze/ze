"""Tests for dream/sleep_pass.py — SleepPass."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_memory.dream.sleep_pass import SleepPass


def _make_pool(episodes=None, sensitive_check=False, entities=None):
    conn = AsyncMock()
    conn.fetch = AsyncMock(side_effect=_fetch_side_effect(episodes or [], entities or []))
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    return pool, conn


def _fetch_side_effect(episodes, entities):
    call_count = [0]

    async def _side_effect(query, *args):
        call_count[0] += 1
        if "memory_episodes" in query and "memory_episode_metadata" in query:
            return episodes
        if "memory_facts" in query:
            return []
        if "memory_entities" in query and "GROUP BY" in query:
            return entities
        return []

    return _side_effect


def _make_sleep_pass(pool=None, episodes=None, entities=None, settings=None):
    if pool is None:
        pool, _ = _make_pool(episodes or [], entities=entities or [])
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=[0.1] * 384)
    consolidator = MagicMock()
    consolidator.archive_session_episodes = AsyncMock(return_value=0)
    consolidator.dedup_facts = AsyncMock(return_value=0)
    dream_store = AsyncMock()
    dream_store.save_artifact = AsyncMock(return_value=uuid4())
    if settings is None:
        settings = {"dream": {"max_replay_episodes": 10, "max_schema_candidates_per_run": 5}}
    return SleepPass(
        pool=pool,
        embedder=embedder,
        consolidator=consolidator,
        dream_store=dream_store,
        settings=settings,
    ), dream_store


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_run_no_episodes_returns_empty_stats():
    sleep_pass, _ = _make_sleep_pass()
    run_id = uuid4()
    with patch.object(sleep_pass, "_check_sensitive_entities", new=AsyncMock(return_value=False)):
        stats = await sleep_pass.run(run_id)
    assert stats["episodes_scored"] == 0
    assert stats["episodes_replayed"] == 0
    assert "duration_ms" in stats


async def test_run_delegates_to_consolidator():
    sleep_pass, _ = _make_sleep_pass()
    run_id = uuid4()
    with patch.object(sleep_pass, "_check_sensitive_entities", new=AsyncMock(return_value=False)):
        await sleep_pass.run(run_id)
    sleep_pass._consolidator.archive_session_episodes.assert_awaited_once()
    sleep_pass._consolidator.dedup_facts.assert_awaited_once()


async def test_schema_candidates_saved_to_dream_store():
    entity_rows = [
        {
            "entity_id": uuid4(),
            "canonical_name": "Acme Corp",
            "sessions": ["s1", "s2", "s3"],
            "episode_ids": [uuid4(), uuid4(), uuid4()],
            "session_count": 3,
        }
    ]

    pool, conn = _make_pool(episodes=[], entities=entity_rows)

    async def _fetch_side(query, *args):
        if "memory_entities" in query and "GROUP BY" in query:
            return entity_rows
        if "memory_facts" in query:
            return []
        if "memory_episodes" in query:
            return []
        return []

    conn.fetch = AsyncMock(side_effect=_fetch_side)

    sleep_pass, dream_store = _make_sleep_pass(pool=pool)
    run_id = uuid4()
    with patch.object(sleep_pass, "_check_sensitive_entities", new=AsyncMock(return_value=False)):
        stats = await sleep_pass.run(run_id)
    assert stats["schema_candidates"] == 1
    dream_store.save_artifact.assert_awaited_once()


async def test_schema_candidates_capped_at_max():
    max_candidates = 2
    entity_rows = [
        {
            "entity_id": uuid4(),
            "canonical_name": f"Entity {i}",
            "sessions": [f"s{i}a", f"s{i}b", f"s{i}c"],
            "episode_ids": [uuid4()],
            "session_count": 3,
        }
        for i in range(5)
    ]

    pool, conn = _make_pool(episodes=[], entities=entity_rows)

    async def _fetch_side(query, *args):
        if "memory_entities" in query and "GROUP BY" in query:
            # Return only max_candidates rows (simulating LIMIT)
            return entity_rows[:max_candidates]
        if "memory_facts" in query:
            return []
        if "memory_episodes" in query:
            return []
        return []

    conn.fetch = AsyncMock(side_effect=_fetch_side)

    settings = {"dream": {"max_schema_candidates_per_run": max_candidates}}
    sleep_pass, dream_store = _make_sleep_pass(pool=pool, settings=settings)
    run_id = uuid4()
    with patch.object(sleep_pass, "_check_sensitive_entities", new=AsyncMock(return_value=False)):
        stats = await sleep_pass.run(run_id)
    assert stats["schema_candidates"] <= max_candidates


async def test_check_sensitive_entities_returns_true_when_sensitive():
    episode_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"exists": True})
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    sleep_pass, _ = _make_sleep_pass(pool=pool)
    result = await sleep_pass._check_sensitive_entities(episode_id)
    assert result is True


async def test_check_sensitive_entities_returns_false_when_none():
    episode_id = uuid4()
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    sleep_pass, _ = _make_sleep_pass(pool=pool)
    result = await sleep_pass._check_sensitive_entities(episode_id)
    assert result is False


async def test_decay_pass_marks_archived_when_weight_drops():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))
    sleep_pass, _ = _make_sleep_pass(pool=pool)
    await sleep_pass._decay_pass({"decay_cycles": 5, "decay_rate": 0.1, "forgetting_weight_threshold": 0.1})
    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args[0][0]
    assert "provenance" in sql
    assert "'archived'" in sql
