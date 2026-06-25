"""Tests for dream/scorer.py — replay_score, _classify_source, _novelty_score."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_memory.dream.scorer import (
    _classify_source,
    _novelty_score,
    replay_score,
    tag_episode_metadata,
)


def _make_episode(
    *,
    sensitive: bool = False,
    relevance: float = 0.0,
    replay_count: int = 0,
    source: str = "ze_observed",
    embedding=None,
    created_at: datetime | None = None,
):
    class Ep:
        pass

    ep = Ep()
    ep.has_sensitive_entity = sensitive
    ep.relevance = relevance
    ep.replay_count = replay_count
    ep.source = source
    ep.embedding = embedding
    ep.created_at = created_at or datetime(2026, 6, 25, tzinfo=timezone.utc)
    return ep


def _make_fact(embedding=None):
    class F:
        pass

    f = F()
    f.embedding = embedding
    return f


# ── replay_score ──────────────────────────────────────────────────────────────

def test_replay_score_sensitive_returns_zero():
    ep = _make_episode(sensitive=True)
    score = replay_score(ep, datetime.now(tz=timezone.utc), [])
    assert score == 0.0


def test_replay_score_user_asserted_half_weight():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    ep_observed = _make_episode(source="ze_observed", created_at=now)
    ep_asserted = _make_episode(source="user_asserted", created_at=now)
    score_obs = replay_score(ep_observed, now, [])
    score_ass = replay_score(ep_asserted, now, [])
    assert math.isclose(score_ass, score_obs * 0.5, rel_tol=1e-6)


def test_replay_score_recent_episode_higher_than_old():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    recent = _make_episode(created_at=datetime(2026, 6, 24, tzinfo=timezone.utc))
    old = _make_episode(created_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert replay_score(recent, now, []) > replay_score(old, now, [])


def test_replay_score_positive_for_normal_episode():
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    ep = _make_episode(created_at=datetime(2026, 6, 20, tzinfo=timezone.utc))
    score = replay_score(ep, now, [])
    assert 0.0 < score <= 1.0


# ── _classify_source ──────────────────────────────────────────────────────────

def test_classify_source_email_agent_is_observed():
    assert _classify_source("email", "", "") == "ze_observed"


def test_classify_source_calendar_agent_is_observed():
    assert _classify_source("calendar_agent", "", "") == "ze_observed"


def test_classify_source_workflow_agent_is_observed():
    assert _classify_source("workflow", "", "") == "ze_observed"


def test_classify_source_companion_no_tools_is_user_asserted():
    assert _classify_source("companion", "what should I eat?", "here are some ideas") == "user_asserted"


def test_classify_source_tool_result_in_response_is_observed():
    assert _classify_source(
        "research",
        "look up X",
        '{"type": "tool_result", "content": "..."}',
    ) == "ze_observed"


def test_classify_source_news_agent_is_observed():
    assert _classify_source("news", "", "") == "ze_observed"


# ── _novelty_score ────────────────────────────────────────────────────────────

def test_novelty_score_no_facts_returns_one():
    assert _novelty_score(None, []) == 1.0


def test_novelty_score_empty_facts_returns_one():
    emb = [1.0, 0.0, 0.0]
    assert _novelty_score(emb, []) == 1.0


def test_novelty_score_identical_embedding_returns_zero():
    emb = [1.0, 0.0, 0.0]
    score = _novelty_score(emb, [emb])
    assert math.isclose(score, 0.0, abs_tol=1e-6)


def test_novelty_score_orthogonal_embedding_returns_one():
    emb_a = [1.0, 0.0, 0.0]
    emb_b = [0.0, 1.0, 0.0]
    score = _novelty_score(emb_a, [emb_b])
    assert math.isclose(score, 1.0, abs_tol=1e-6)


# ── tag_episode_metadata ──────────────────────────────────────────────────────

async def test_tag_episode_metadata_inserts_row():
    from uuid import uuid4

    episode_id = uuid4()
    conn = AsyncMock()
    conn.execute = AsyncMock()
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))

    await tag_episode_metadata(pool, episode_id, "companion", "hello", "world")
    conn.execute.assert_awaited_once()
    call_args = conn.execute.call_args
    assert "memory_episode_metadata" in call_args[0][0]


async def test_tag_episode_metadata_swallows_db_error():
    from uuid import uuid4

    episode_id = uuid4()
    conn = AsyncMock()
    conn.execute = AsyncMock(side_effect=Exception("db down"))
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(
        __aenter__=AsyncMock(return_value=conn),
        __aexit__=AsyncMock(return_value=False),
    ))

    # Should not raise
    await tag_episode_metadata(pool, episode_id, "companion", "hello", "world")
