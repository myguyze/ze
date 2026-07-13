from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


from ze_automation.goals.executor import GoalExecutor
from ze_automation.goals.types import (
    Goal,
    GoalStatus,
    Milestone,
    MilestoneStatus,
)
from ze_agents.interface.types import Notification


def _goal() -> Goal:
    return Goal(
        id=uuid4(),
        title="Build product",
        objective="Ship MVP",
        success_condition="First customer",
        status=GoalStatus.ACTIVE,
    )


def _milestone(seq=1, reuse_hint="") -> Milestone:
    return Milestone(
        id=uuid4(),
        goal_id=uuid4(),
        title=f"Step {seq}",
        description=f"Do step {seq}",
        sequence=seq,
        status=MilestoneStatus.PENDING,
        reuse_hint=reuse_hint,
    )


def _make_executor(push=None):
    push = push or AsyncMock()
    executor = GoalExecutor(
        goal_store=AsyncMock(),
        goal_planner=AsyncMock(),
        push=push,
        agent_getter=MagicMock(return_value=AsyncMock()),
    )
    return executor, push


# ── _push_reuse_notice ────────────────────────────────────────────────────────


async def test_push_reuse_notice_sends_notification():
    executor, push = _make_executor()
    goal = _goal()
    milestone = _milestone(
        reuse_hint="Prior goal 'Market Research' produced competitor list (5 days ago)."
    )

    await executor._push_reuse_notice(goal, milestone)

    push.assert_called_once()
    notification: Notification = push.call_args[0][0]
    assert "Prior work reused" in notification.content
    assert goal.title in notification.content
    assert milestone.title in notification.content
    assert "Market Research" in notification.content
    assert notification.urgency == "low"
    assert notification.format == "html"


async def test_push_reuse_notice_includes_hint_content():
    executor, push = _make_executor()
    goal = _goal()
    hint = "Prior goal 'XYZ' already did the research (10 days ago). Reuse if current."
    milestone = _milestone(reuse_hint=hint)

    await executor._push_reuse_notice(goal, milestone)

    notification: Notification = push.call_args[0][0]
    assert "XYZ" in notification.content


# ── advance integration: reuse notice fires on completion ──────────────────────


async def test_advance_fires_reuse_notice_when_hint_set():
    push = AsyncMock()
    store = AsyncMock()
    goal = _goal()
    m = _milestone(seq=1, reuse_hint="Prior goal 'Old Goal' produced market research.")
    m.goal_id = goal.id

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.update_milestone = AsyncMock()
    store.save_traces = AsyncMock()
    store.reset_consecutive_failures = AsyncMock()
    store.add_learning = AsyncMock()
    store.append_learnings = AsyncMock()
    store.list_active = AsyncMock(return_value=[goal])

    agent_mock = AsyncMock()
    agent_result = MagicMock()
    agent_result.response = "Done"
    agent_result.tool_calls = []
    agent_mock.run = AsyncMock(return_value=agent_result)

    planner = AsyncMock()
    planner.extract_learning = AsyncMock(return_value="Key insight.")

    executor = GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=MagicMock(return_value=agent_mock),
    )

    with patch("asyncio.create_task") as mock_task:
        await executor._advance_unlocked(goal.id)

    # create_task should have been called for: save_traces and reuse notice (at minimum)
    task_calls = [str(c) for c in mock_task.call_args_list]
    assert any("reuse_notice" in c or "_push_reuse_notice" in c for c in task_calls), (
        f"Expected _push_reuse_notice task, got: {task_calls}"
    )


async def test_advance_does_not_fire_reuse_notice_when_hint_empty():
    push = AsyncMock()
    store = AsyncMock()
    goal = _goal()
    m = _milestone(seq=1, reuse_hint="")
    m.goal_id = goal.id

    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[m])
    store.get_pending_gate = AsyncMock(return_value=None)
    store.update_milestone = AsyncMock()
    store.save_traces = AsyncMock()
    store.reset_consecutive_failures = AsyncMock()
    store.add_learning = AsyncMock()
    store.append_learnings = AsyncMock()

    agent_mock = AsyncMock()
    agent_result = MagicMock()
    agent_result.response = "Done"
    agent_result.tool_calls = []
    agent_mock.run = AsyncMock(return_value=agent_result)

    planner = AsyncMock()
    planner.extract_learning = AsyncMock(return_value="Key insight.")

    executor = GoalExecutor(
        goal_store=store,
        goal_planner=planner,
        push=push,
        agent_getter=MagicMock(return_value=agent_mock),
    )

    with patch("asyncio.create_task") as mock_task:
        await executor._advance_unlocked(goal.id)

    task_calls = [str(c) for c in mock_task.call_args_list]
    assert not any("reuse_notice" in c or "_push_reuse_notice" in c for c in task_calls)
