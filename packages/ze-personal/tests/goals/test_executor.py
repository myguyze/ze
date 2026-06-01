from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from ze_core.errors import GoalExecutionError
from ze_personal.goals.executor import GoalExecutor
from ze_personal.goals.types import (
    Goal,
    GoalLearning,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    VerificationGate,
)
from ze_core.interface.types import Notification


def _goal(status=GoalStatus.ACTIVE, **kwargs) -> Goal:
    return Goal(
        id=uuid4(),
        title="Test Goal",
        objective="Do something",
        success_condition="It is done",
        status=status,
        **kwargs,
    )


def _milestone(seq: int, status=MilestoneStatus.PENDING, goal_id=None) -> Milestone:
    return Milestone(
        id=uuid4(),
        goal_id=goal_id or uuid4(),
        title=f"Step {seq}",
        description=f"Do step {seq}",
        sequence=seq,
        status=status,
    )


def _gate(after_seq: int, goal_id=None, status=GateStatus.PENDING) -> VerificationGate:
    return VerificationGate(
        id=uuid4(),
        goal_id=goal_id or uuid4(),
        after_sequence=after_seq,
        title="Checkpoint",
        status=status,
    )


@pytest.fixture
def store():
    s = AsyncMock()
    s.get_goal = AsyncMock(return_value=None)
    s.list_milestones = AsyncMock(return_value=[])
    s.update_milestone = AsyncMock()
    s.update_status = AsyncMock()
    s.get_pending_gate = AsyncMock(return_value=None)
    s.add_learning = AsyncMock()
    s.append_learnings = AsyncMock()
    s.fire_gate = AsyncMock()
    s.replace_pending_milestones = AsyncMock(return_value=[])
    s.replace_pending_gates = AsyncMock(return_value=[])
    s.resolve_gate = AsyncMock()
    s.get_gate = AsyncMock(return_value=None)
    return s


@pytest.fixture
def planner():
    p = AsyncMock()
    p.extract_learning = AsyncMock(return_value="Key insight.")
    p.replan_remaining = AsyncMock(return_value=([], []))
    return p


@pytest.fixture
def push():
    return AsyncMock()


@pytest.fixture
def agent_mock():
    a = AsyncMock()
    result = MagicMock()
    result.response = "Milestone output"
    a.run = AsyncMock(return_value=result)
    return a


@pytest.fixture
def agent_getter(agent_mock):
    return lambda name: agent_mock


@pytest.fixture
def executor(store, planner, push, agent_getter):
    return GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=agent_getter,
    )


async def test_advance_skips_non_active_goal(executor, store):
    goal_id = uuid4()
    store.get_goal = AsyncMock(return_value=_goal(status=GoalStatus.PAUSED))
    await executor.advance(goal_id)
    store.list_milestones.assert_not_called()


async def test_advance_marks_goal_completed_when_no_pending(executor, store, push):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    await executor.advance(goal.id)
    store.update_status.assert_called_with(goal.id, GoalStatus.COMPLETED)
    push.assert_called_once()
    notif = push.call_args.args[0]
    assert isinstance(notif, Notification)
    assert "complete" in notif.content.lower()


async def test_advance_executes_next_pending_milestone(executor, store, push, agent_mock):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    store.update_milestone.assert_any_call(m1.id, MilestoneStatus.IN_PROGRESS)
    store.update_milestone.assert_any_call(m1.id, MilestoneStatus.COMPLETED, output="Milestone output")


async def test_advance_skips_milestone_on_execution_error(executor, store, push, agent_mock):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    agent_mock.run = AsyncMock(side_effect=Exception("network error"))

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    store.update_milestone.assert_any_call(m1.id, MilestoneStatus.SKIPPED, output=pytest.approx("Failed: Milestone 1 (Step 1) failed: network error", abs=100))


async def test_gate_fires_before_next_milestone(executor, store, push):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = _gate(after_seq=1, goal_id=goal.id)

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1, m2])
    store.get_pending_gate = AsyncMock(return_value=gate)

    await executor.advance(goal.id)

    store.fire_gate.assert_called_once()
    store.update_status.assert_called_with(goal.id, GoalStatus.AWAITING_GATE)
    notif = push.call_args.args[0]
    assert len(notif.actions) == 3  # Proceed, Stop, Redirect


async def test_gate_does_not_fire_if_prior_not_done(executor, store, push):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.IN_PROGRESS, goal_id=goal.id)
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = _gate(after_seq=1, goal_id=goal.id)

    store.get_goal = AsyncMock(return_value=goal)
    # After the reset, return both as pending
    store.list_milestones = AsyncMock(side_effect=[
        [m1, m2],  # first call — detects stuck milestone
        [_milestone(1, MilestoneStatus.PENDING, goal_id=goal.id), m2],  # after reset
    ])
    store.get_pending_gate = AsyncMock(return_value=gate)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    store.fire_gate.assert_not_called()


async def test_approve_plan_activates_goal(executor, store):
    goal = _goal(status=GoalStatus.PLANNING)
    store.get_goal = AsyncMock(return_value=goal)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        result = await executor.approve_plan(goal.id)

    assert result is True
    store.update_status.assert_called_with(goal.id, GoalStatus.ACTIVE)


async def test_approve_plan_returns_false_if_not_planning(executor, store):
    goal = _goal(status=GoalStatus.ACTIVE)
    store.get_goal = AsyncMock(return_value=goal)
    result = await executor.approve_plan(goal.id)
    assert result is False


async def test_reject_plan_abandons_goal(executor, store):
    goal = _goal(status=GoalStatus.PLANNING)
    store.get_goal = AsyncMock(return_value=goal)
    result = await executor.reject_plan(goal.id)
    assert result is True
    store.update_status.assert_called_with(goal.id, GoalStatus.ABANDONED)


async def test_handle_gate_approved(executor, store):
    goal = _goal()
    gate = _gate(after_seq=1, goal_id=goal.id, status=GateStatus.AWAITING_APPROVAL)
    store.get_gate = AsyncMock(return_value=gate)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.handle_gate_approved(gate.id)

    store.resolve_gate.assert_called_with(gate.id, GateStatus.APPROVED)
    store.update_status.assert_called_with(goal.id, GoalStatus.ACTIVE)


async def test_handle_gate_stopped(executor, store, push):
    goal = _goal()
    gate = _gate(after_seq=1, goal_id=goal.id, status=GateStatus.AWAITING_APPROVAL)
    store.get_gate = AsyncMock(return_value=gate)
    store.get_goal = AsyncMock(return_value=goal)

    await executor.handle_gate_stopped(gate.id)

    store.resolve_gate.assert_called_with(gate.id, GateStatus.STOPPED)
    store.update_status.assert_called_with(goal.id, GoalStatus.ABANDONED)
    push.assert_called_once()
