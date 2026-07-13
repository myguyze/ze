from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4


from ze_automation.goals.planner import GoalPlanner
from ze_automation.goals.types import Goal, GoalStatus


def _goal(title="Launch SaaS", objective="Build and ship an MVP") -> Goal:
    return Goal(
        id=uuid4(),
        title=title,
        objective=objective,
        success_condition="First paying customer",
        status=GoalStatus.ACTIVE,
    )


def _planner(response: str) -> GoalPlanner:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return GoalPlanner(client=client, model="test-model")


def _convergence_json(goal: Goal, description: str, suggestion: str) -> str:
    return json.dumps(
        {
            "overlapping_goal_id": str(goal.id),
            "overlapping_goal_title": goal.title,
            "overlap_description": description,
            "suggestion": suggestion,
        }
    )


# ── detect_convergence ────────────────────────────────────────────────────────


async def test_detect_convergence_returns_convergence_on_overlap():
    active = _goal(
        title="Research SaaS competitors", objective="Identify top 10 SaaS competitors"
    )
    planner = _planner(
        _convergence_json(active, "Both goals research SaaS market.", "share outputs")
    )

    result = await planner.detect_convergence(_goal(), [active])

    assert result is not None
    assert result.overlapping_goal_id == active.id
    assert result.overlapping_goal_title == active.title
    assert "SaaS" in result.overlap_description
    assert result.suggestion == "share outputs"


async def test_detect_convergence_returns_none_on_null_response():
    planner = _planner(json.dumps({"overlapping_goal_id": None}))
    result = await planner.detect_convergence(_goal(), [_goal(title="Other goal")])
    assert result is None


async def test_detect_convergence_returns_none_with_empty_active_list():
    client = AsyncMock()
    client.complete = AsyncMock()
    planner = GoalPlanner(client=client, model="test-model")

    result = await planner.detect_convergence(_goal(), [])

    client.complete.assert_not_called()
    assert result is None


async def test_detect_convergence_returns_none_on_malformed_json():
    planner = _planner("not json at all")
    result = await planner.detect_convergence(_goal(), [_goal()])
    assert result is None


async def test_detect_convergence_returns_none_on_llm_exception():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))
    planner = GoalPlanner(client=client, model="test-model")

    result = await planner.detect_convergence(_goal(), [_goal()])
    assert result is None


async def test_detect_convergence_truncates_long_fields():
    active = _goal()
    long_description = "x" * 500
    long_suggestion = "y" * 200
    planner = _planner(
        json.dumps(
            {
                "overlapping_goal_id": str(active.id),
                "overlapping_goal_title": active.title,
                "overlap_description": long_description,
                "suggestion": long_suggestion,
            }
        )
    )

    result = await planner.detect_convergence(_goal(), [active])

    assert result is not None
    assert len(result.overlap_description) <= 300
    assert len(result.suggestion) <= 100
