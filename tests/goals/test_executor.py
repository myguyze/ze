import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze.goals.executor import GoalExecutor
from ze.goals.types import (
    Goal,
    GoalLearning,
    GoalStatus,
    GateStatus,
    Milestone,
    MilestoneStatus,
    VerificationGate,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_goal(**overrides) -> Goal:
    defaults = dict(
        id=uuid4(),
        title="My Goal",
        objective="obj",
        success_condition="done",
        status=GoalStatus.ACTIVE,
    )
    defaults.update(overrides)
    return Goal(**defaults)


def make_milestone(sequence: int, status: MilestoneStatus = MilestoneStatus.PENDING, **overrides) -> Milestone:
    goal_id = overrides.pop("goal_id", uuid4())
    return Milestone(
        id=uuid4(),
        goal_id=goal_id,
        title=f"Step {sequence}",
        description=f"Do step {sequence}",
        sequence=sequence,
        status=status,
        **overrides,
    )


def make_gate(after_sequence: int, status: GateStatus = GateStatus.PENDING, **overrides) -> VerificationGate:
    goal_id = overrides.pop("goal_id", uuid4())
    return VerificationGate(
        id=uuid4(),
        goal_id=goal_id,
        after_sequence=after_sequence,
        title=f"Gate after {after_sequence}",
        status=status,
        **overrides,
    )


def make_executor(goal_store=None, goal_planner=None, notifier=None):
    if goal_store is None:
        goal_store = MagicMock()
        goal_store.get_goal = AsyncMock(return_value=None)
        goal_store.list_milestones = AsyncMock(return_value=[])
        goal_store.get_pending_gate = AsyncMock(return_value=None)
        goal_store.update_status = AsyncMock()
        goal_store.update_milestone = AsyncMock()
        goal_store.add_learning = AsyncMock()
        goal_store.append_learnings = AsyncMock()
        goal_store.fire_gate = AsyncMock()
        goal_store.get_gate = AsyncMock(return_value=None)
        goal_store.resolve_gate = AsyncMock()
        goal_store.replace_pending_milestones = AsyncMock(return_value=[])
        goal_store.create_gate = AsyncMock()

    if goal_planner is None:
        goal_planner = MagicMock()
        goal_planner.extract_learning = AsyncMock(return_value="A useful insight.")
        goal_planner.replan_remaining = AsyncMock(return_value=([], []))

    if notifier is None:
        notifier = MagicMock()
        notifier.push = AsyncMock()
        notifier.push_with_keyboard = AsyncMock()

    return GoalExecutor(
        goal_store=goal_store,
        goal_planner=goal_planner,
        notifier=notifier,
    )


# ── advance: non-active goal ──────────────────────────────────────────────────

async def test_advance_returns_early_if_goal_not_active():
    store = MagicMock()
    store.get_goal = AsyncMock(return_value=make_goal(status=GoalStatus.PAUSED))
    store.list_milestones = AsyncMock(return_value=[])
    executor = make_executor(goal_store=store)
    await executor.advance(uuid4())
    store.list_milestones.assert_not_called()


async def test_advance_returns_early_if_goal_not_found():
    store = MagicMock()
    store.get_goal = AsyncMock(return_value=None)
    store.list_milestones = AsyncMock(return_value=[])
    executor = make_executor(goal_store=store)
    await executor.advance(uuid4())
    store.list_milestones.assert_not_called()


# ── advance: completion ───────────────────────────────────────────────────────

async def test_advance_marks_completed_when_no_pending_milestones():
    goal = make_goal()
    store = MagicMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        make_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.update_status = AsyncMock()
    notifier = MagicMock()
    notifier.push = AsyncMock()
    executor = make_executor(goal_store=store, notifier=notifier)
    await executor.advance(goal.id)
    store.update_status.assert_awaited_once_with(goal.id, GoalStatus.COMPLETED)
    notifier.push.assert_awaited_once()


# ── advance: gate firing ──────────────────────────────────────────────────────

async def test_advance_fires_gate_when_due():
    goal = make_goal()
    m1 = make_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id, output="done")
    m2 = make_milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = make_gate(1, GateStatus.PENDING, goal_id=goal.id)

    store = MagicMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1, m2])
    store.get_pending_gate = AsyncMock(return_value=gate)
    store.fire_gate = AsyncMock()
    store.update_status = AsyncMock()
    notifier = MagicMock()
    notifier.push_with_keyboard = AsyncMock()

    executor = make_executor(goal_store=store, notifier=notifier)
    await executor.advance(goal.id)

    store.fire_gate.assert_awaited_once()
    store.update_status.assert_awaited_once_with(goal.id, GoalStatus.AWAITING_GATE)
    notifier.push_with_keyboard.assert_awaited_once()


# ── advance: milestone execution ──────────────────────────────────────────────

async def test_advance_executes_pending_milestone():
    goal = make_goal()
    m1 = make_milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)

    store = MagicMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.update_milestone = AsyncMock()
    store.add_learning = AsyncMock()
    store.append_learnings = AsyncMock()
    store.update_status = AsyncMock()
    notifier = MagicMock()
    notifier.push = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(response="Done."))

    executor = make_executor(goal_store=store, notifier=notifier)

    with patch("ze.goals.executor.get_agent", return_value=mock_agent):
        # advance will recursively create_task — cancel it by making list_milestones
        # return all completed on second call
        store.list_milestones.side_effect = [
            [m1],
            [make_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)],
        ]
        # Run only the first iteration
        call_count = 0
        orig_advance = executor.advance

        async def limited_advance(gid):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                return
            await orig_advance(gid)

        executor.advance = limited_advance
        await executor.advance(goal.id)

    store.update_milestone.assert_awaited()


# ── advance: failed milestone ──────────────────────────────────────────────────

async def test_advance_skips_milestone_on_failure():
    goal = make_goal()
    m1 = make_milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)

    store = MagicMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.update_milestone = AsyncMock()
    store.add_learning = AsyncMock()
    store.update_status = AsyncMock()
    notifier = MagicMock()
    notifier.push = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(side_effect=Exception("agent crashed"))

    executor = make_executor(goal_store=store, notifier=notifier)

    with patch("ze.goals.executor.get_agent", return_value=mock_agent):
        # Prevent recursive advance
        advance_calls = []
        orig = executor.advance
        async def once(gid):
            advance_calls.append(gid)
            if len(advance_calls) == 1:
                await orig(gid)
        executor.advance = once
        await executor.advance(goal.id)

    # Should mark as SKIPPED with error output
    update_call = store.update_milestone.call_args_list
    assert any(MilestoneStatus.SKIPPED in c.args for c in update_call)


# ── gate: approve / stop / redirect ───────────────────────────────────────────

async def test_advance_does_not_fire_gate_before_prior_milestone_done():
    goal = make_goal()
    m1 = make_milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = make_gate(1, GateStatus.PENDING, goal_id=goal.id)

    store = MagicMock()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=gate)
    store.update_milestone = AsyncMock()
    store.add_learning = AsyncMock()
    store.append_learnings = AsyncMock()

    mock_agent = MagicMock()
    mock_agent.run = AsyncMock(return_value=MagicMock(response="Done."))
    executor = make_executor(goal_store=store)

    with patch("ze.goals.executor.get_agent", return_value=mock_agent):
        advance_calls = []
        orig = executor.advance
        async def once(gid):
            advance_calls.append(gid)
            if len(advance_calls) == 1:
                await orig(gid)
        executor.advance = once
        await executor.advance(goal.id)

    store.fire_gate.assert_not_called()


async def test_handle_gate_approved_sets_active_and_advances():
    goal_id = uuid4()
    gate = make_gate(1, GateStatus.AWAITING_APPROVAL, goal_id=goal_id)
    gate.goal_id = goal_id

    store = MagicMock()
    store.get_gate = AsyncMock(return_value=gate)
    store.resolve_gate = AsyncMock()
    store.update_status = AsyncMock()
    # Prevent real advance from running
    store.get_goal = AsyncMock(return_value=None)

    executor = make_executor(goal_store=store)
    await executor.handle_gate_approved(gate.id)

    store.resolve_gate.assert_awaited_once_with(gate.id, GateStatus.APPROVED)
    store.update_status.assert_awaited_once_with(goal_id, GoalStatus.ACTIVE)


async def test_handle_gate_approved_ignores_already_resolved_gate():
    gate = make_gate(1, GateStatus.APPROVED, goal_id=uuid4())
    store = MagicMock()
    store.get_gate = AsyncMock(return_value=gate)
    store.resolve_gate = AsyncMock()
    store.update_status = AsyncMock()
    executor = make_executor(goal_store=store)
    await executor.handle_gate_approved(gate.id)
    store.resolve_gate.assert_not_called()


async def test_handle_gate_stopped_abandons_goal():
    goal = make_goal()
    gate = make_gate(1, GateStatus.AWAITING_APPROVAL, goal_id=goal.id)
    gate.goal_id = goal.id

    store = MagicMock()
    store.get_gate = AsyncMock(return_value=gate)
    store.get_goal = AsyncMock(return_value=goal)
    store.resolve_gate = AsyncMock()
    store.update_status = AsyncMock()
    notifier = MagicMock()
    notifier.push = AsyncMock()

    executor = make_executor(goal_store=store, notifier=notifier)
    await executor.handle_gate_stopped(gate.id)

    store.resolve_gate.assert_awaited_once_with(gate.id, GateStatus.STOPPED)
    store.update_status.assert_awaited_once_with(goal.id, GoalStatus.ABANDONED)
    notifier.push.assert_awaited_once()
