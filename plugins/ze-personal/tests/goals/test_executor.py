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
    s.save_traces = AsyncMock()
    s.reset_consecutive_failures = AsyncMock()
    s.increment_consecutive_failures = AsyncMock(return_value=1)
    s.increment_replan_count = AsyncMock(return_value=1)
    s.list_learnings = AsyncMock(return_value=[])
    s.save_retrospective = AsyncMock()
    s.list_completed_milestone_summaries = AsyncMock(return_value=[])
    return s


@pytest.fixture
def planner():
    p = AsyncMock()
    p.extract_learning = AsyncMock(return_value="Key insight.")
    p.replan_remaining = AsyncMock(return_value=([], []))
    p.synthesize_gate_narrative = AsyncMock(return_value="Work was completed successfully.")
    p.synthesize_retrospective = AsyncMock(return_value="Goal completed successfully.")
    p.promote_learnings = AsyncMock(return_value=[])
    p.extract_procedure = AsyncMock(return_value=None)
    return p


@pytest.fixture
def push():
    return AsyncMock()


@pytest.fixture
def agent_mock():
    a = AsyncMock()
    result = MagicMock()
    result.response = "Milestone output"
    result.tool_calls = []
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


# ── _build_milestone_prompt ───────────────────────────────────────────────────

def test_build_milestone_prompt_no_prior_steps():
    from ze_personal.goals.executor import _build_milestone_prompt

    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    prompt = _build_milestone_prompt(m1, goal, [m1])

    assert "[GOAL CONTEXT]" in prompt
    assert "Test Goal" in prompt
    assert "(no prior steps)" in prompt
    assert "[YOUR TASK]" in prompt
    assert "Do step 1" in prompt


def test_build_milestone_prompt_with_completed_steps():
    from ze_personal.goals.executor import _build_milestone_prompt

    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m1.output = "Research complete"
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)

    prompt = _build_milestone_prompt(m2, goal, [m1, m2])

    assert "Research complete" in prompt
    assert "(no prior steps)" not in prompt
    assert "step 2 of 2" in prompt


def test_build_milestone_prompt_truncates_older_steps():
    from ze_personal.goals.executor import _build_milestone_prompt

    goal = _goal()
    milestones = []
    for i in range(1, 6):
        m = _milestone(i, MilestoneStatus.COMPLETED if i < 5 else MilestoneStatus.PENDING, goal_id=goal.id)
        m.output = "x" * 600
        milestones.append(m)

    pending = milestones[-1]
    prompt = _build_milestone_prompt(pending, goal, milestones)

    # Older steps (seq 1) are capped at 100 chars; recent ones (seq 2,3,4) at 500
    # The 600-char output should be truncated in both cases
    assert "x" * 501 not in prompt  # no output exceeds 500 chars
    assert "[YOUR TASK]" in prompt


def test_build_milestone_prompt_includes_learnings():
    from ze_personal.goals.executor import _build_milestone_prompt

    goal = _goal(learnings="Key insight from last week")
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    prompt = _build_milestone_prompt(m1, goal, [m1])

    assert "Key insight from last week" in prompt


def test_build_milestone_prompt_no_learnings_shows_placeholder():
    from ze_personal.goals.executor import _build_milestone_prompt

    goal = _goal()  # learnings=""
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    prompt = _build_milestone_prompt(m1, goal, [m1])

    assert "(none yet)" in prompt


# ── Adaptive replan ───────────────────────────────────────────────────────────

async def test_adaptive_replan_triggers_at_two_consecutive_failures(executor, store, push, agent_mock, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.increment_consecutive_failures = AsyncMock(return_value=2)
    store.increment_replan_count = AsyncMock(return_value=1)
    planner.replan_remaining = AsyncMock(return_value=([_milestone(1, goal_id=goal.id)], []))
    agent_mock.run = AsyncMock(side_effect=Exception("timeout"))

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    planner.replan_remaining.assert_called_once()
    store.replace_pending_milestones.assert_called_once()
    # First push is the "Two steps failed" message
    first_notif = push.call_args_list[0].args[0]
    assert "two steps failed" in first_notif.content.lower() or "adapting" in first_notif.content.lower()


async def test_adaptive_replan_not_triggered_at_one_failure(executor, store, push, agent_mock, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.increment_consecutive_failures = AsyncMock(return_value=1)
    agent_mock.run = AsyncMock(side_effect=Exception("timeout"))

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    planner.replan_remaining.assert_not_called()


async def test_adaptive_replan_cap_pauses_goal_after_second_replan(executor, store, push, agent_mock):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.increment_consecutive_failures = AsyncMock(return_value=2)
    store.increment_replan_count = AsyncMock(return_value=2)  # already replanned once
    agent_mock.run = AsyncMock(side_effect=Exception("still failing"))

    await executor.advance(goal.id)

    store.update_status.assert_called_with(goal.id, GoalStatus.PAUSED)
    notif = push.call_args.args[0]
    assert "paused" in notif.content.lower()


async def test_success_resets_consecutive_failures(executor, store, push, agent_mock):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    store.reset_consecutive_failures.assert_called_once_with(goal.id)


# ── Gate narrative ────────────────────────────────────────────────────────────

async def test_gate_uses_synthesized_narrative(executor, store, push, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = _gate(after_seq=1, goal_id=goal.id)

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1, m2])
    store.get_pending_gate = AsyncMock(return_value=gate)
    planner.synthesize_gate_narrative = AsyncMock(return_value="The first phase is complete.")

    await executor.advance(goal.id)

    planner.synthesize_gate_narrative.assert_called_once()
    notif = push.call_args.args[0]
    assert "The first phase is complete." in notif.content


async def test_gate_falls_back_to_bullet_list_on_narrative_timeout(executor, store, push, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m1.output = "Research done"
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = _gate(after_seq=1, goal_id=goal.id)

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1, m2])
    store.get_pending_gate = AsyncMock(return_value=gate)
    planner.synthesize_gate_narrative = AsyncMock(side_effect=asyncio.TimeoutError())

    await executor.advance(goal.id)

    notif = push.call_args.args[0]
    # Fallback uses bullet list
    assert "Step 1" in notif.content


async def test_gate_falls_back_to_bullet_list_on_narrative_error(executor, store, push, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m1.output = "Research done"
    m2 = _milestone(2, MilestoneStatus.PENDING, goal_id=goal.id)
    gate = _gate(after_seq=1, goal_id=goal.id)

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1, m2])
    store.get_pending_gate = AsyncMock(return_value=gate)
    planner.synthesize_gate_narrative = AsyncMock(side_effect=RuntimeError("LLM down"))

    await executor.advance(goal.id)

    notif = push.call_args.args[0]
    assert "Step 1" in notif.content


# ── Steer ─────────────────────────────────────────────────────────────────────

async def test_steer_enqueues_instruction_for_active_goal(executor, store):
    goal = _goal(status=GoalStatus.ACTIVE)
    store.get_goal = AsyncMock(return_value=goal)

    result = await executor.steer(goal.id, "Skip the LinkedIn step")

    assert result is True
    assert not executor._steer_queues[goal.id].empty()


async def test_steer_returns_false_for_non_active_goal(executor, store):
    goal = _goal(status=GoalStatus.PAUSED)
    store.get_goal = AsyncMock(return_value=goal)

    result = await executor.steer(goal.id, "some instruction")

    assert result is False


async def test_steer_returns_false_for_awaiting_gate_goal(executor, store):
    goal = _goal(status=GoalStatus.AWAITING_GATE)
    store.get_goal = AsyncMock(return_value=goal)

    result = await executor.steer(goal.id, "steer me")

    assert result is False


async def test_advance_drains_steer_before_milestone(executor, store, push, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    planner.replan_remaining = AsyncMock(return_value=([_milestone(1, goal_id=goal.id)], []))

    # Pre-load a steer instruction
    await executor._steer_queues[goal.id].put("focus on email only")

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor.advance(goal.id)

    planner.replan_remaining.assert_called_once()
    store.replace_pending_milestones.assert_called_once()
    # Queue should be empty after draining
    assert executor._steer_queues[goal.id].empty()


async def test_apply_steer_pauses_on_replan_failure(executor, store, push, planner):
    goal = _goal()
    store.list_milestones = AsyncMock(return_value=[])
    planner.replan_remaining = AsyncMock(side_effect=RuntimeError("LLM error"))

    await executor._apply_steer(goal.id, goal, "new direction")

    store.update_status.assert_called_with(goal.id, GoalStatus.PAUSED)
    notif = push.call_args.args[0]
    assert "paused" in notif.content.lower()


# ── Retrospective ─────────────────────────────────────────────────────────────

async def test_completion_pushes_retrospective(executor, store, push, planner):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(side_effect=[
        [_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)],  # stuck check
        [_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)],  # pending check → none
        [_milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)],  # retrospective fetch
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    planner.synthesize_retrospective = AsyncMock(return_value="You accomplished the objective.")

    await executor.advance(goal.id)

    planner.synthesize_retrospective.assert_called_once()
    notif = push.call_args.args[0]
    assert "completed" in notif.content.lower()
    assert "You accomplished the objective." in notif.content


async def test_retrospective_failure_falls_back_to_success_condition(executor, store, push, planner):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    planner.synthesize_retrospective = AsyncMock(side_effect=RuntimeError("LLM down"))

    await executor.advance(goal.id)

    notif = push.call_args.args[0]
    assert goal.success_condition in notif.content


async def test_push_retrospective_calls_save_retrospective(executor, store, push, planner):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.save_retrospective = AsyncMock()
    planner.synthesize_retrospective = AsyncMock(return_value="Accomplished the goal successfully.")

    await executor.advance(goal.id)

    store.save_retrospective.assert_called_once_with(goal.id, "Accomplished the goal successfully.")


async def test_push_retrospective_still_pushes_when_save_retrospective_fails(executor, store, push, planner):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.save_retrospective = AsyncMock(side_effect=RuntimeError("DB write failed"))
    planner.synthesize_retrospective = AsyncMock(return_value="Accomplished the goal successfully.")

    await executor.advance(goal.id)

    push.assert_called_once()
    notif = push.call_args.args[0]
    assert "Accomplished the goal successfully." in notif.content


# ── Task state sync ───────────────────────────────────────────────────────────

@pytest.fixture
def memory_store():
    m = AsyncMock()
    m.upsert_task_state = AsyncMock()
    return m


@pytest.fixture
def executor_with_memory(store, planner, push, agent_getter, memory_store):
    return GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=agent_getter,
        memory_store=memory_store,
    )


async def test_task_state_written_on_milestone_start(executor_with_memory, store, memory_store):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor_with_memory.advance(goal.id)

    memory_store.upsert_task_state.assert_called()
    call_args = memory_store.upsert_task_state.call_args_list
    statuses = [c.args[0].status for c in call_args]
    assert "in_progress" in statuses


async def test_task_state_written_as_completed_when_no_pending(executor_with_memory, store, memory_store, push, planner):
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    planner.synthesize_retrospective = AsyncMock(return_value="Done.")

    await executor_with_memory.advance(goal.id)

    memory_store.upsert_task_state.assert_called()
    call_args = memory_store.upsert_task_state.call_args_list
    statuses = [c.args[0].status for c in call_args]
    assert "completed" in statuses


async def test_task_state_written_as_blocked_on_double_failure(executor_with_memory, store, memory_store, push, planner):
    goal = _goal()
    m1 = _milestone(1, MilestoneStatus.PENDING, goal_id=goal.id)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m1])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.increment_consecutive_failures = AsyncMock(return_value=2)
    store.increment_replan_count = AsyncMock(return_value=2)

    # Agent raises so milestone is skipped/failed
    from ze_core.errors import GoalExecutionError
    from ze_core.orchestration.types import AgentContext, AgentResult

    failing_agent = AsyncMock()
    failing_agent.run = AsyncMock(side_effect=GoalExecutionError("tool failed"))
    executor_with_memory._get_agent = lambda name: failing_agent

    with patch("ze_personal.goals.executor.asyncio.create_task"):
        await executor_with_memory.advance(goal.id)

    memory_store.upsert_task_state.assert_called()
    call_args = memory_store.upsert_task_state.call_args_list
    statuses = [c.args[0].status for c in call_args]
    assert "blocked" in statuses


async def test_task_state_sync_skipped_when_no_memory_store(executor, store, push, planner):
    """The default executor fixture has no memory_store — no error should occur."""
    goal = _goal()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id),
    ])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    planner.synthesize_retrospective = AsyncMock(return_value="Done.")

    # Must not raise
    await executor.advance(goal.id)
