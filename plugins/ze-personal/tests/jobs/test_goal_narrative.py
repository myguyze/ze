from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.jobs.goal_narrative import GoalNarrativeJob
from ze_personal.goals.types import Goal, GoalStatus, Milestone, MilestoneStatus, VerificationGate, GateStatus


def _goal(title="Test Goal", status=GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id=uuid4(), title=title, objective="o", success_condition="s", status=status,
    )


def _milestone(seq: int, status=MilestoneStatus.COMPLETED, completed_at=None) -> Milestone:
    m = Milestone(
        id=uuid4(), goal_id=uuid4(), title=f"Step {seq}",
        description="d", sequence=seq, status=status,
    )
    m.completed_at = completed_at or datetime.now(timezone.utc)
    return m


def _gate(title="Checkpoint") -> VerificationGate:
    return VerificationGate(
        id=uuid4(), goal_id=uuid4(), after_sequence=1,
        title=title, status=GateStatus.AWAITING_APPROVAL,
    )


def _make_job(goals=None, milestones=None, gate=None, dedup=False, paragraph="Progress summary."):
    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()

    push_log = AsyncMock()
    push_log.was_sent_within_hours = AsyncMock(return_value=dedup)
    push_log.log = AsyncMock()

    goal_store = AsyncMock()
    goal_store.list_active = AsyncMock(return_value=goals or [])
    goal_store.list_milestones = AsyncMock(return_value=milestones or [])
    goal_store.get_pending_gate = AsyncMock(return_value=gate)

    planner = AsyncMock()
    planner.synthesize_weekly_narrative = AsyncMock(return_value=paragraph)

    job = GoalNarrativeJob(
        notifier=notifier,
        push_log_store=push_log,
        goal_store=goal_store,
        goal_planner=planner,
    )
    return job, notifier, push_log, planner


# ── Deduplication ─────────────────────────────────────────────────────────────

async def test_run_skips_when_dedup_within_6_days():
    job, notifier, _, _ = _make_job(dedup=True)
    await job.run()
    notifier.push_notification.assert_not_called()


# ── No active goals ───────────────────────────────────────────────────────────

async def test_run_skips_when_no_active_goals():
    job, notifier, _, _ = _make_job(goals=[])
    await job.run()
    notifier.push_notification.assert_not_called()


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_run_sends_narrative_for_goals_with_progress():
    goal = _goal("Job search")
    m1 = _milestone(1, MilestoneStatus.COMPLETED)

    job, notifier, push_log, planner = _make_job(
        goals=[goal],
        milestones=[m1],
        paragraph="Ze found 10 prospects this week.",
    )

    await job.run()

    planner.synthesize_weekly_narrative.assert_called_once()
    notifier.push_notification.assert_called_once()
    notif = notifier.push_notification.call_args.args[0]
    assert "Job search" in notif.content
    assert "Ze found 10 prospects" in notif.content
    push_log.log.assert_called_once_with("goal_narrative", "weekly")


async def test_run_skips_goals_with_no_progress_this_week():
    now = datetime.now(timezone.utc)
    from datetime import timedelta
    old_date = now - timedelta(days=10)

    goal = _goal("Stale Goal")
    m1 = _milestone(1, MilestoneStatus.COMPLETED, completed_at=old_date)

    job, notifier, _, planner = _make_job(goals=[goal], milestones=[m1])

    await job.run()

    planner.synthesize_weekly_narrative.assert_not_called()
    notifier.push_notification.assert_not_called()


# ── Awaiting gate ─────────────────────────────────────────────────────────────

async def test_run_includes_awaiting_gate_even_without_weekly_progress():
    goal = _goal("Spanish learning", status=GoalStatus.AWAITING_GATE)
    gate = _gate("Week 1 review")

    job, notifier, _, planner = _make_job(
        goals=[goal],
        milestones=[],
        gate=gate,
        paragraph="Awaiting your review.",
    )

    await job.run()

    planner.synthesize_weekly_narrative.assert_called_once()
    notif = notifier.push_notification.call_args.args[0]
    assert "Week 1 review" in notif.content


# ── Resilience ────────────────────────────────────────────────────────────────

async def test_run_continues_when_one_goal_narrative_fails():
    goal1 = _goal("Goal A")
    goal2 = _goal("Goal B")
    m = _milestone(1, MilestoneStatus.COMPLETED)

    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()
    push_log = AsyncMock()
    push_log.was_sent_within_hours = AsyncMock(return_value=False)
    push_log.log = AsyncMock()
    goal_store = AsyncMock()
    goal_store.list_active = AsyncMock(return_value=[goal1, goal2])
    goal_store.list_milestones = AsyncMock(return_value=[m])
    goal_store.get_pending_gate = AsyncMock(return_value=None)
    planner = AsyncMock()
    planner.synthesize_weekly_narrative = AsyncMock(
        side_effect=[RuntimeError("LLM error"), "Goal B is progressing well."]
    )

    job = GoalNarrativeJob(
        notifier=notifier,
        push_log_store=push_log,
        goal_store=goal_store,
        goal_planner=planner,
    )
    await job.run()

    # Goal B paragraph should still be sent
    notifier.push_notification.assert_called_once()
    notif = notifier.push_notification.call_args.args[0]
    assert "Goal B" in notif.content
    assert "Goal A" not in notif.content
