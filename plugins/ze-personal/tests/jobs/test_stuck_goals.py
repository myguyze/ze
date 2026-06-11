from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest

from ze_personal.jobs.stuck_goals import StuckGoalJob, _build_message
from ze_personal.goals.types import Goal, GoalStatus, StuckGoal, VerificationGate, GateStatus


def _goal(title: str = "Learn Rust") -> Goal:
    return Goal(
        id=uuid4(),
        title=title,
        objective="Build a CLI tool in Rust",
        success_condition="CLI tool compiles and runs",
        status=GoalStatus.ACTIVE,
    )


def _gate(goal_id) -> VerificationGate:
    return VerificationGate(
        id=uuid4(),
        goal_id=goal_id,
        after_sequence=2,
        title="Mid-point review",
        status=GateStatus.PENDING,
    )


def _active_stuck(title: str = "Learn Rust", idle_days: int = 10) -> StuckGoal:
    g = _goal(title)
    return StuckGoal(
        goal=g,
        kind="active",
        idle_days=idle_days,
        last_milestone_title="Set up Rust toolchain",
        gate=None,
    )


def _gate_stuck(title: str = "Launch website", idle_days: int = 12) -> StuckGoal:
    g = Goal(
        id=uuid4(),
        title=title,
        objective="Launch personal portfolio",
        success_condition="Site is live",
        status=GoalStatus.AWAITING_GATE,
    )
    return StuckGoal(
        goal=g,
        kind="awaiting_gate",
        idle_days=idle_days,
        last_milestone_title="Built homepage",
        gate=_gate(g.id),
    )


def _make_job(*, stuck: list[StuckGoal], push_raises: bool = False):
    notifier = AsyncMock()
    if push_raises:
        notifier.push_notification = AsyncMock(side_effect=RuntimeError("push failed"))
    else:
        notifier.push_notification = AsyncMock()

    goal_store = AsyncMock()
    goal_store.list_stuck = AsyncMock(return_value=stuck)
    goal_store.mark_stuck_alerted = AsyncMock()

    job = object.__new__(StuckGoalJob)
    job._notifier = notifier
    job._goal_store = goal_store
    return job, notifier, goal_store


# ── StuckGoalJob.run ──────────────────────────────────────────────────────────

async def test_run_no_op_when_no_stuck_goals():
    job, notifier, goal_store = _make_job(stuck=[])
    await job.run()
    notifier.push_notification.assert_not_called()
    goal_store.mark_stuck_alerted.assert_not_called()


async def test_run_sends_notification_when_stuck_goals_found():
    sg = _active_stuck()
    job, notifier, _ = _make_job(stuck=[sg])
    await job.run()
    notifier.push_notification.assert_called_once()


async def test_run_marks_all_goals_alerted_after_push():
    sg1 = _active_stuck("Goal A")
    sg2 = _gate_stuck("Goal B")
    job, _, goal_store = _make_job(stuck=[sg1, sg2])
    await job.run()
    goal_store.mark_stuck_alerted.assert_any_call(sg1.goal.id)
    goal_store.mark_stuck_alerted.assert_any_call(sg2.goal.id)
    assert goal_store.mark_stuck_alerted.call_count == 2


async def test_run_does_not_mark_alerted_if_push_fails():
    sg = _active_stuck()
    job, _, goal_store = _make_job(stuck=[sg], push_raises=True)
    with pytest.raises(RuntimeError):
        await job.run()
    goal_store.mark_stuck_alerted.assert_not_called()


# ── _build_message ────────────────────────────────────────────────────────────

def test_build_message_single_active_omits_number_from_labels():
    sg = _active_stuck()
    _, actions = _build_message([sg])
    labels = [a.label for a in actions]
    assert "Redirect" in labels
    assert "Pause" in labels
    assert "Abandon" in labels
    assert not any("#1" in lbl for lbl in labels)


def test_build_message_multiple_goals_includes_number():
    sg1 = _active_stuck("Goal A")
    sg2 = _gate_stuck("Goal B")
    _, actions = _build_message([sg1, sg2])
    labels = [a.label for a in actions]
    assert any("#1" in lbl for lbl in labels)
    assert any("#2" in lbl for lbl in labels)


def test_build_message_header_singular():
    sg = _active_stuck()
    content, _ = _build_message([sg])
    assert "One of your goals needs attention" in content


def test_build_message_header_plural():
    sg1 = _active_stuck("A")
    sg2 = _gate_stuck("B")
    content, _ = _build_message([sg1, sg2])
    assert "2 of your goals need attention" in content


def test_build_message_awaiting_gate_buttons():
    sg = _gate_stuck()
    _, actions = _build_message([sg])
    labels = [a.label for a in actions]
    assert any("Approve" in lbl for lbl in labels)
    assert any("Redirect" in lbl for lbl in labels)
    assert any("Stop" in lbl for lbl in labels)
    assert not any("Pause" in lbl for lbl in labels)
    assert not any("Abandon" in lbl for lbl in labels)


def test_build_message_active_buttons():
    sg = _active_stuck()
    _, actions = _build_message([sg])
    labels = [a.label for a in actions]
    assert any("Redirect" in lbl for lbl in labels)
    assert any("Pause" in lbl for lbl in labels)
    assert any("Abandon" in lbl for lbl in labels)
    assert not any("Approve" in lbl for lbl in labels)
    assert not any("Stop" in lbl for lbl in labels)


def test_build_message_no_last_milestone():
    g = _goal()
    sg = StuckGoal(goal=g, kind="active", idle_days=8, last_milestone_title=None, gate=None)
    content, _ = _build_message([sg])
    assert "No steps completed yet" in content


def test_build_message_uses_full_uuid_hex_in_payload():
    sg = _active_stuck()
    _, actions = _build_message([sg])
    for a in actions:
        assert sg.goal.id.hex in a.payload


def test_build_message_payloads_under_64_bytes():
    sg1 = _active_stuck()
    sg2 = _gate_stuck()
    for sg in [sg1, sg2]:
        _, actions = _build_message([sg])
        for a in actions:
            assert len(a.payload.encode()) <= 64, f"Payload too long: {a.payload!r}"
