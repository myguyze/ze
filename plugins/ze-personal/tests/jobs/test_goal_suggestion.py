from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.jobs.goal_suggestion import GoalSuggestionJob
from ze_personal.goals.types import GoalSuggestion, SuggestionStatus


def _suggestion() -> GoalSuggestion:
    return GoalSuggestion(
        id=uuid4(),
        title="Learn Spanish",
        objective="Achieve conversational fluency within 6 months.",
        rationale="Based on your retrospective for 'Travel to South America', language was the main barrier in Argentina 2024.",
        source_type="retrospective",
        source_ref="Travel to South America",
        status=SuggestionStatus.PENDING,
        suggested_at=datetime.now(timezone.utc),
    )


_SENTINEL = object()


def _make_job(
    *,
    expired=0,
    suggested_recently=False,
    suggestion=None,
    save_result=True,
    push_raises=False,
    signal_raises=False,
    first_suggestion=True,
):
    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()

    suggestion_store = AsyncMock()
    suggestion_store.expire_stale_pending = AsyncMock(return_value=expired)
    # Call order: (1) dedup check, (2) first-ness check (before save)
    # first_suggestion=True means was_suggested_recently returns False on call 2 → is_first=True
    # first_suggestion=False means was_suggested_recently returns True on call 2 → is_first=False
    suggestion_store.was_suggested_recently = AsyncMock(
        side_effect=[suggested_recently, not first_suggestion]
    )
    suggestion_store.save = AsyncMock(return_value=save_result)
    suggestion_store.mark_expired = AsyncMock()

    goal_store = AsyncMock()
    if signal_raises:
        goal_store.list_retrospectives = AsyncMock(side_effect=RuntimeError("DB error"))
    else:
        goal_store.list_retrospectives = AsyncMock(return_value=[])
        goal_store.list_active_goal_titles = AsyncMock(return_value=[])

    memory_store = AsyncMock()
    memory_store.list_recent_facts = AsyncMock(return_value=[])
    memory_store.list_recent_episodes = AsyncMock(return_value=[])

    planner = AsyncMock()
    planner.generate_suggestion = AsyncMock(return_value=suggestion)

    if push_raises:
        notifier.push_notification = AsyncMock(side_effect=RuntimeError("Telegram down"))

    job = GoalSuggestionJob(
        notifier=notifier,
        goal_store=goal_store,
        suggestion_store=suggestion_store,
        planner=planner,
        memory_store=memory_store,
    )
    return job, notifier, suggestion_store, planner


# ── step 0: expire stale ──────────────────────────────────────────────────────

async def test_run_expires_stale_before_dedup_check():
    job, _, suggestion_store, _ = _make_job(suggested_recently=True, expired=2)
    await job.run()
    suggestion_store.expire_stale_pending.assert_called_once_with(older_than_days=30)


# ── step 1: dedup ─────────────────────────────────────────────────────────────

async def test_run_skips_when_suggested_recently():
    job, notifier, suggestion_store, planner = _make_job(suggested_recently=True)
    await job.run()
    planner.generate_suggestion.assert_not_called()
    notifier.push_notification.assert_not_called()


# ── step 2: signal read failure ───────────────────────────────────────────────

async def test_run_exits_cleanly_when_signal_read_raises():
    job, notifier, _, planner = _make_job(signal_raises=True)
    await job.run()
    planner.generate_suggestion.assert_not_called()
    notifier.push_notification.assert_not_called()


# ── step 3: no suggestion from planner ───────────────────────────────────────

async def test_run_skips_when_generate_suggestion_returns_none():
    job, notifier, suggestion_store, _ = _make_job(suggestion=None)
    await job.run()
    suggestion_store.save.assert_not_called()
    notifier.push_notification.assert_not_called()


# ── step 4: week conflict ─────────────────────────────────────────────────────

async def test_run_exits_when_save_returns_false_week_conflict():
    job, notifier, suggestion_store, _ = _make_job(
        suggestion=_suggestion(), save_result=False,
    )
    await job.run()
    suggestion_store.save.assert_called_once()
    notifier.push_notification.assert_not_called()


# ── step 5: push failure ──────────────────────────────────────────────────────

async def test_run_calls_mark_expired_when_push_fails():
    s = _suggestion()
    job, _, suggestion_store, _ = _make_job(
        suggestion=s, push_raises=True,
    )
    await job.run()
    suggestion_store.mark_expired.assert_called_once_with(s.id)


# ── happy path ────────────────────────────────────────────────────────────────

async def test_run_saves_suggestion_and_pushes_notification():
    s = _suggestion()
    job, notifier, suggestion_store, _ = _make_job(suggestion=s)
    await job.run()

    suggestion_store.save.assert_called_once()
    week_key = suggestion_store.save.call_args.args[1]
    assert week_key.startswith("20")  # ISO week format

    notifier.push_notification.assert_called_once()
    notif = notifier.push_notification.call_args.args[0]
    assert "Learn Spanish" in notif.content
    assert len(notif.actions) == 3


async def test_first_suggestion_includes_intro_sentence():
    s = _suggestion()
    job, notifier, _, _ = _make_job(suggestion=s, first_suggestion=True)
    await job.run()

    notif = notifier.push_notification.call_args.args[0]
    assert "Here's a goal idea" in notif.content


async def test_subsequent_suggestion_omits_intro_sentence():
    s = _suggestion()
    # first_suggestion=False means was_suggested_recently returns True on the second call
    job, notifier, _, _ = _make_job(suggestion=s, first_suggestion=False)
    await job.run()

    notif = notifier.push_notification.call_args.args[0]
    assert "Here's a goal idea" not in notif.content


async def test_run_uses_correct_callback_payloads():
    s = _suggestion()
    job, notifier, _, _ = _make_job(suggestion=s)
    await job.run()

    notif = notifier.push_notification.call_args.args[0]
    short_id = s.id.hex[:8]
    payloads = [a.payload for a in notif.actions]
    assert f"goal_suggest:accept:{short_id}" in payloads
    assert f"goal_suggest:dismiss:{short_id}" in payloads
    assert f"goal_suggest:more:{short_id}" in payloads


async def test_run_keyboard_layout_has_two_rows():
    s = _suggestion()
    job, notifier, _, _ = _make_job(suggestion=s)
    await job.run()

    notif = notifier.push_notification.call_args.args[0]
    rows = {a.row for a in notif.actions}
    assert rows == {0, 1}  # accept+dismiss in row 0, tell-me-more in row 1
