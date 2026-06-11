from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ze_personal.goals.types import Goal, GoalStatus, PriorMilestoneOutput


def _goal() -> Goal:
    return Goal(
        id=uuid4(),
        title="New Goal",
        objective="Achieve something great",
        success_condition="It is achieved",
        status=GoalStatus.PLANNING,
    )


def _prior() -> PriorMilestoneOutput:
    return PriorMilestoneOutput(
        goal_id=uuid4(),
        goal_title="Past Goal",
        milestone_id=uuid4(),
        milestone_title="Research done",
        output_snippet="Found useful info.",
        completed_days_ago=14,
    )


def _make_deps(
    *,
    prior_work=None,
    prior_work_raises=False,
    plan_raises=False,
    milestones=None,
    gates=None,
):
    from ze_personal.goals.types import Milestone, MilestoneStatus, VerificationGate, GateStatus

    store = AsyncMock()
    store.list_completed_milestone_summaries = (
        AsyncMock(side_effect=RuntimeError("DB down"))
        if prior_work_raises
        else AsyncMock(return_value=prior_work or [])
    )
    created_goal = _goal()
    store.create_goal = AsyncMock(return_value=created_goal)
    store.create_milestone = AsyncMock()
    store.create_gate = AsyncMock()

    from ze_core.errors import GoalPlanError
    planner = AsyncMock()
    if plan_raises:
        planner.plan = AsyncMock(side_effect=GoalPlanError("LLM failed"))
    else:
        ms = milestones or [
            Milestone(
                id=uuid4(), goal_id=created_goal.id,
                title="Step 1", description="Do it",
                sequence=1, status=MilestoneStatus.PENDING,
            )
        ]
        gs = gates or [
            VerificationGate(
                id=uuid4(), goal_id=created_goal.id,
                after_sequence=1, title="Review",
                status=GateStatus.PENDING,
            )
        ]
        planner.plan = AsyncMock(return_value=(ms, gs))

    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()

    return store, planner, notifier


# ── create_goal: prior work query ─────────────────────────────────────────────

async def test_create_goal_queries_prior_work_before_planning():
    from ze_personal.agents.goals.tools import create_goal

    pw = _prior()
    store, planner, notifier = _make_deps(prior_work=[pw])

    await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    store.list_completed_milestone_summaries.assert_called_once()


async def test_create_goal_passes_prior_work_to_planner():
    from ze_personal.agents.goals.tools import create_goal

    pw = _prior()
    store, planner, notifier = _make_deps(prior_work=[pw])

    await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    call_kwargs = planner.plan.call_args.kwargs
    assert call_kwargs.get("prior_work") == [pw]


async def test_create_goal_passes_none_when_no_prior_work():
    from ze_personal.agents.goals.tools import create_goal

    store, planner, notifier = _make_deps(prior_work=[])

    await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    call_kwargs = planner.plan.call_args.kwargs
    assert call_kwargs.get("prior_work") is None


async def test_create_goal_continues_normally_when_prior_work_query_raises():
    from ze_personal.agents.goals.tools import create_goal

    store, planner, notifier = _make_deps(prior_work_raises=True)

    result = await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    assert "error" not in result
    planner.plan.assert_called_once()


async def test_create_goal_passes_none_prior_work_when_query_raises():
    from ze_personal.agents.goals.tools import create_goal

    store, planner, notifier = _make_deps(prior_work_raises=True)

    await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    call_kwargs = planner.plan.call_args.kwargs
    assert call_kwargs.get("prior_work") is None


async def test_create_goal_returns_error_when_plan_fails():
    from ze_personal.agents.goals.tools import create_goal

    store, planner, notifier = _make_deps(plan_raises=True)

    result = await create_goal(
        store=store,
        planner=planner,
        notifier=notifier,
        goal_title="New Goal",
        objective="obj",
        success_condition="done",
    )

    assert "error" in result
