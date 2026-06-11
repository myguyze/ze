from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.goals.suggestion_store import GoalSuggestionStore
from ze_personal.goals.types import GoalSuggestion, SuggestionStatus


def _make_pool(fetchrow=None, fetch=None, execute=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.execute = AsyncMock(return_value=execute or "UPDATE 0")

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def _suggestion(status=SuggestionStatus.PENDING, **kwargs) -> GoalSuggestion:
    return GoalSuggestion(
        id=uuid4(),
        title="Learn Spanish",
        objective="Achieve conversational fluency in Spanish within 6 months.",
        rationale="Based on your retrospective for 'Travel to South America', you identified language as the main barrier.",
        source_type="retrospective",
        source_ref="Travel to South America",
        status=status,
        suggested_at=datetime.now(timezone.utc),
        **kwargs,
    )


def _row(suggestion: GoalSuggestion) -> dict:
    return {
        "id": suggestion.id,
        "title": suggestion.title,
        "objective": suggestion.objective,
        "rationale": suggestion.rationale,
        "source_type": suggestion.source_type,
        "source_ref": suggestion.source_ref,
        "status": suggestion.status.value,
        "suggested_at": suggestion.suggested_at,
        "resolved_at": suggestion.resolved_at,
        "created_goal_id": suggestion.created_goal_id,
    }


# ── save ──────────────────────────────────────────────────────────────────────

async def test_save_returns_true_on_insert():
    s = _suggestion()
    row = MagicMock()
    row.__getitem__ = lambda self, key: s.id
    pool, conn = _make_pool(fetchrow=row)
    store = GoalSuggestionStore(pool)

    result = await store.save(s, "2026-W23")

    assert result is True
    conn.fetchrow.assert_called_once()
    sql = conn.fetchrow.call_args.args[0]
    assert "ON CONFLICT (week_key) DO NOTHING" in sql


async def test_save_returns_false_on_week_key_conflict():
    s = _suggestion()
    pool, conn = _make_pool(fetchrow=None)  # RETURNING returns no row on conflict
    store = GoalSuggestionStore(pool)

    result = await store.save(s, "2026-W23")

    assert result is False


# ── mark_accepted ─────────────────────────────────────────────────────────────

async def test_mark_accepted_returns_true_on_first_call():
    s = _suggestion()
    goal_id = uuid4()
    row = MagicMock()
    pool, conn = _make_pool(fetchrow=row)
    store = GoalSuggestionStore(pool)

    result = await store.mark_accepted(s.id, goal_id)

    assert result is True
    sql = conn.fetchrow.call_args.args[0]
    assert "status = 'pending'" in sql
    assert "accepted" in sql


async def test_mark_accepted_returns_false_on_second_call():
    s = _suggestion()
    goal_id = uuid4()
    pool, conn = _make_pool(fetchrow=None)
    store = GoalSuggestionStore(pool)

    result = await store.mark_accepted(s.id, goal_id)

    assert result is False


# ── mark_dismissed ────────────────────────────────────────────────────────────

async def test_mark_dismissed_returns_true_when_pending():
    s = _suggestion()
    row = MagicMock()
    pool, conn = _make_pool(fetchrow=row)
    store = GoalSuggestionStore(pool)

    result = await store.mark_dismissed(s.id)

    assert result is True
    sql = conn.fetchrow.call_args.args[0]
    assert "status = 'pending'" in sql
    assert "dismissed" in sql


async def test_mark_dismissed_returns_false_when_already_accepted():
    s = _suggestion(status=SuggestionStatus.ACCEPTED)
    pool, conn = _make_pool(fetchrow=None)
    store = GoalSuggestionStore(pool)

    result = await store.mark_dismissed(s.id)

    assert result is False


# ── expire_stale_pending ──────────────────────────────────────────────────────

async def test_expire_stale_pending_returns_count():
    pool, conn = _make_pool(execute="UPDATE 3")
    store = GoalSuggestionStore(pool)

    count = await store.expire_stale_pending(older_than_days=30)

    assert count == 3
    sql = conn.execute.call_args.args[0]
    assert "status = 'pending'" in sql
    assert "expired" in sql


async def test_expire_stale_pending_does_not_affect_resolved():
    pool, conn = _make_pool(execute="UPDATE 0")
    store = GoalSuggestionStore(pool)

    count = await store.expire_stale_pending(older_than_days=30)

    assert count == 0
    sql = conn.execute.call_args.args[0]
    assert "status = 'pending'" in sql  # only touches PENDING rows


# ── was_suggested_recently ────────────────────────────────────────────────────

async def test_was_suggested_recently_returns_true_for_pending_within_window():
    row = MagicMock()
    pool, conn = _make_pool(fetchrow=row)
    store = GoalSuggestionStore(pool)

    result = await store.was_suggested_recently(days=30)

    assert result is True
    sql = conn.fetchrow.call_args.args[0]
    assert "pending" in sql
    assert "accepted" in sql
    assert "dismissed" in sql


async def test_was_suggested_recently_returns_false_outside_window():
    pool, conn = _make_pool(fetchrow=None)
    store = GoalSuggestionStore(pool)

    result = await store.was_suggested_recently(days=30)

    assert result is False


async def test_was_suggested_recently_excludes_expired():
    pool, conn = _make_pool(fetchrow=None)
    store = GoalSuggestionStore(pool)

    await store.was_suggested_recently(days=30)

    sql = conn.fetchrow.call_args.args[0]
    assert "expired" not in sql.lower().split("in")[1] if "IN" in sql.upper() else True
    # The query filters status IN ('pending', 'accepted', 'dismissed') — expired not included
    assert "'expired'" not in sql


# ── resolve_short_id ──────────────────────────────────────────────────────────

async def test_resolve_short_id_finds_suggestion_by_prefix():
    s = _suggestion()
    row = _row(s)
    pool, conn = _make_pool(fetch=[row])
    store = GoalSuggestionStore(pool)

    result = await store.resolve_short_id(s.id.hex[:8])

    assert result is not None
    assert result.id == s.id


async def test_resolve_short_id_returns_none_on_multiple_pending():
    s1 = _suggestion()
    s2 = _suggestion()
    rows = [_row(s1), _row(s2)]
    # Both have status='pending'
    pool, conn = _make_pool(fetch=rows)
    store = GoalSuggestionStore(pool)

    result = await store.resolve_short_id("abcd1234")

    assert result is None


async def test_resolve_short_id_returns_none_when_not_found():
    pool, conn = _make_pool(fetch=[])
    store = GoalSuggestionStore(pool)

    result = await store.resolve_short_id("00000000")

    assert result is None
