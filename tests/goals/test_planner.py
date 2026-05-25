import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from ze.errors import GoalPlanError
from ze.goals.planner import GoalPlanner
from ze.goals.types import Goal


def make_planner(response: str = ""):
    client = MagicMock()
    client.complete = AsyncMock(return_value=response)
    settings = MagicMock()
    settings.workflow_plan_model = "some-model"
    return GoalPlanner(openrouter_client=client, settings=settings)


def make_goal(**overrides) -> Goal:
    defaults = dict(
        title="Build prospect list",
        objective="Find 20 charter operators in Portugal",
        success_condition="List of 20 contacts with emails",
        time_horizon="2 weeks",
    )
    defaults.update(overrides)
    return Goal(**defaults)


_VALID_PLAN = json.dumps({
    "milestones": [
        {"title": "Research operators", "description": "Use research agent", "agent_hint": "research", "intent": "read", "sequence": 1},
        {"title": "Build contact list", "description": "Compile contacts", "agent_hint": "companion", "intent": "reason", "sequence": 2},
        {"title": "Send outreach", "description": "Send emails", "agent_hint": "email", "intent": "execute", "sequence": 3},
    ],
    "gates": [
        {"after_sequence": 2, "title": "Review contacts before outreach"},
    ],
})


async def test_plan_returns_milestones_and_gates():
    planner = make_planner(_VALID_PLAN)
    goal = make_goal()
    milestones, gates = await planner.plan(goal)
    assert len(milestones) == 3
    assert len(gates) == 1


async def test_plan_milestones_sorted_by_sequence():
    # Reverse order in JSON, must come out sorted
    data = {
        "milestones": [
            {"title": "C", "description": "c", "agent_hint": None, "intent": "read", "sequence": 3},
            {"title": "A", "description": "a", "agent_hint": None, "intent": "read", "sequence": 1},
            {"title": "B", "description": "b", "agent_hint": None, "intent": "read", "sequence": 2},
        ],
        "gates": [{"after_sequence": 2, "title": "Checkpoint"}],
    }
    planner = make_planner(json.dumps(data))
    milestones, _ = await planner.plan(make_goal())
    assert [m.sequence for m in milestones] == [1, 2, 3]


async def test_plan_uses_sentinel_goal_id():
    planner = make_planner(_VALID_PLAN)
    milestones, gates = await planner.plan(make_goal())
    sentinel = UUID("00000000-0000-0000-0000-000000000000")
    for m in milestones:
        assert m.goal_id == sentinel
    for g in gates:
        assert g.goal_id == sentinel


async def test_plan_raises_on_invalid_json():
    planner = make_planner("not json at all")
    with pytest.raises(GoalPlanError):
        await planner.plan(make_goal())


async def test_plan_raises_on_empty_milestones():
    planner = make_planner(json.dumps({"milestones": [], "gates": []}))
    with pytest.raises(GoalPlanError):
        await planner.plan(make_goal())


async def test_plan_requires_at_least_one_gate():
    data = {
        "milestones": [
            {"title": "A", "description": "a", "agent_hint": None, "intent": "read", "sequence": 1},
        ],
        "gates": [],
    }
    planner = make_planner(json.dumps(data))
    with pytest.raises(GoalPlanError, match="gate"):
        await planner.plan(make_goal())


async def test_replan_normalizes_sequences_to_next_sequence():
    data = {
        "milestones": [
            {"title": "B", "description": "b", "agent_hint": None, "intent": "read", "sequence": 1},
            {"title": "C", "description": "c", "agent_hint": None, "intent": "read", "sequence": 2},
        ],
        "gates": [{"after_sequence": 1, "title": "Check"}],
    }
    planner = make_planner(json.dumps(data))
    milestones, gates = await planner.replan_remaining(make_goal(), [], "focus on Spain", next_sequence=3)
    assert [m.sequence for m in milestones] == [3, 4]
    assert gates[0].after_sequence == 3


async def test_plan_raises_on_non_object_response():
    planner = make_planner(json.dumps([{"title": "x"}]))
    with pytest.raises(GoalPlanError):
        await planner.plan(make_goal())


async def test_extract_learning_returns_text():
    planner = make_planner("Found 15 operators in Porto.")
    result = await planner.extract_learning("Research step", "output text")
    assert result == "Found 15 operators in Porto."
