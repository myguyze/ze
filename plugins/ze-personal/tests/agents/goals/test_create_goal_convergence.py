from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4

import pytest

from ze_personal.agents.goals.tools import _check_convergence
from ze_automation.goals.types import Goal, GoalConvergence, GoalStatus
from ze_agents.interface.types import Notification


def _goal(title="Find leads", objective="Build a list of contacts") -> Goal:
    return Goal(
        id=uuid4(),
        title=title,
        objective=objective,
        success_condition="Done",
        status=GoalStatus.ACTIVE,
    )


def _make_planner(convergence: GoalConvergence | None = None) -> AsyncMock:
    planner = AsyncMock()
    planner.detect_convergence = AsyncMock(return_value=convergence)
    return planner


def _make_notifier() -> AsyncMock:
    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()
    return notifier


# ── _check_convergence ────────────────────────────────────────────────────────

async def test_check_convergence_pushes_notification_when_overlap_found():
    active = _goal(title="Research SaaS market")
    new_goal = _goal(title="Survey SaaS competitors")
    conv = GoalConvergence(
        overlapping_goal_id=active.id,
        overlapping_goal_title=active.title,
        overlap_description="Both goals research the SaaS competitive landscape.",
        suggestion="share outputs",
    )
    planner = _make_planner(convergence=conv)
    notifier = _make_notifier()

    await _check_convergence(AsyncMock(), planner, notifier, new_goal, [active])

    notifier.push_notification.assert_called_once()
    notification: Notification = notifier.push_notification.call_args[0][0]
    assert "Goal overlap detected" in notification.content
    assert new_goal.title in notification.content
    assert active.title in notification.content
    assert "SaaS competitive landscape" in notification.content
    assert "share outputs" in notification.content
    assert notification.urgency == "normal"
    assert notification.format == "html"


async def test_check_convergence_does_not_push_when_no_overlap():
    planner = _make_planner(convergence=None)
    notifier = _make_notifier()

    await _check_convergence(AsyncMock(), planner, notifier, _goal(), [_goal(title="Unrelated goal")])

    notifier.push_notification.assert_not_called()


async def test_check_convergence_does_not_push_when_active_list_empty():
    planner = _make_planner(convergence=None)
    notifier = _make_notifier()

    await _check_convergence(AsyncMock(), planner, notifier, _goal(), [])

    planner.detect_convergence.assert_not_called()
    notifier.push_notification.assert_not_called()


async def test_check_convergence_filters_out_new_goal_from_candidates():
    new_goal = _goal()
    active_others = [_goal(title="Other goal")]
    planner = _make_planner(convergence=None)
    notifier = _make_notifier()

    await _check_convergence(AsyncMock(), planner, notifier, new_goal, [new_goal, *active_others])

    _, call_args, _ = planner.detect_convergence.mock_calls[0]
    passed_goals = call_args[1]
    assert new_goal not in passed_goals
    assert active_others[0] in passed_goals


async def test_check_convergence_swallows_detect_exception():
    planner = AsyncMock()
    planner.detect_convergence = AsyncMock(side_effect=RuntimeError("LLM error"))
    notifier = _make_notifier()

    # Should not raise
    await _check_convergence(AsyncMock(), planner, notifier, _goal(), [_goal(title="Other")])

    notifier.push_notification.assert_not_called()
