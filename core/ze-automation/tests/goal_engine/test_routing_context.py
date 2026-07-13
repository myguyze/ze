from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4


from ze_automation.goals.types import (
    Goal,
    GoalStatus,
    Milestone,
    MilestoneStatus,
    VerificationGate,
    GateStatus,
)
from ze_automation.graph.routing_context import (
    _build_routing_hints,
    inject_goal_routing_context,
)


def _goal(title: str, status=GoalStatus.ACTIVE) -> Goal:
    return Goal(
        id=uuid4(),
        title=title,
        objective="o",
        success_condition="s",
        status=status,
    )


def _milestone(
    seq: int, status=MilestoneStatus.PENDING, title=None, goal_id=None
) -> Milestone:
    return Milestone(
        id=uuid4(),
        goal_id=goal_id or uuid4(),
        title=title or f"Step {seq}",
        description="d",
        sequence=seq,
        status=status,
    )


def _gate(title: str, goal_id=None) -> VerificationGate:
    return VerificationGate(
        id=uuid4(),
        goal_id=goal_id or uuid4(),
        after_sequence=1,
        title=title,
        status=GateStatus.AWAITING_APPROVAL,
    )


def _make_store(goals=None, milestones_map=None, gate_map=None):
    store = AsyncMock()
    store.list_active = AsyncMock(return_value=goals or [])
    store.list_milestones = AsyncMock(
        side_effect=lambda gid: milestones_map.get(gid, []) if milestones_map else []
    )
    store.get_pending_gate = AsyncMock(
        side_effect=lambda gid: gate_map.get(gid) if gate_map else None
    )
    return store


# ── _build_routing_hints ──────────────────────────────────────────────────────


async def test_build_hints_returns_none_when_no_active_goals():
    store = _make_store(goals=[])
    result = await _build_routing_hints(store)
    assert result is None


async def test_build_hints_includes_active_goal_with_pending_milestone():
    goal = _goal("Job search outreach")
    m1 = _milestone(1, MilestoneStatus.COMPLETED, goal_id=goal.id)
    m2 = _milestone(
        2, MilestoneStatus.PENDING, title="LinkedIn outreach", goal_id=goal.id
    )
    store = _make_store(goals=[goal], milestones_map={goal.id: [m1, m2]})

    result = await _build_routing_hints(store)

    assert result is not None
    assert "Job search outreach" in result
    assert "LinkedIn outreach" in result
    assert result.startswith("[Active goals:")


async def test_build_hints_shows_in_progress_milestone_over_pending():
    goal = _goal("My Goal")
    m1 = _milestone(
        1, MilestoneStatus.IN_PROGRESS, title="Running now", goal_id=goal.id
    )
    m2 = _milestone(2, MilestoneStatus.PENDING, title="Next up", goal_id=goal.id)
    store = _make_store(goals=[goal], milestones_map={goal.id: [m1, m2]})

    result = await _build_routing_hints(store)

    assert "Running now" in result
    assert "Next up" not in result


async def test_build_hints_for_awaiting_gate_goal():
    goal = _goal("Learn Spanish", status=GoalStatus.AWAITING_GATE)
    gate = _gate("Week 1 review", goal_id=goal.id)
    store = _make_store(goals=[goal], gate_map={goal.id: gate})

    result = await _build_routing_hints(store)

    assert "Learn Spanish" in result
    assert "Week 1 review" in result
    assert "awaiting gate" in result.lower()


async def test_build_hints_caps_at_three_goals():
    goals = [_goal(f"Goal {i}") for i in range(5)]
    milestones_map = {g.id: [_milestone(1, goal_id=g.id)] for g in goals}
    store = _make_store(goals=goals, milestones_map=milestones_map)

    result = await _build_routing_hints(store)

    assert result is not None
    assert "Goal 0" in result
    assert "Goal 2" in result
    assert "Goal 3" not in result  # capped at 3


async def test_build_hints_truncates_at_300_chars():
    goal = _goal("A" * 200)
    m = _milestone(1, MilestoneStatus.PENDING, title="B" * 200, goal_id=goal.id)
    store = _make_store(goals=[goal], milestones_map={goal.id: [m]})

    result = await _build_routing_hints(store)

    assert result is not None
    assert len(result) <= 300


async def test_build_hints_goal_with_no_milestones():
    goal = _goal("Empty Goal")
    store = _make_store(goals=[goal], milestones_map={goal.id: []})

    result = await _build_routing_hints(store)

    assert result is not None
    assert "Empty Goal" in result
    assert "step" not in result


# ── inject_goal_routing_context node ─────────────────────────────────────────


async def test_inject_returns_none_when_no_goal_store():
    config = {"configurable": {}}
    state = {"prompt": "hello", "session_id": "x"}
    result = await inject_goal_routing_context(state, config)
    assert result == {"routing_hints": None}


async def test_inject_returns_none_when_no_active_goals():
    store = _make_store(goals=[])
    config = {"configurable": {"goal_store": store}}
    state = {"prompt": "hello", "session_id": "x"}
    result = await inject_goal_routing_context(state, config)
    assert result == {"routing_hints": None}


async def test_inject_returns_hints_when_active_goals_exist():
    goal = _goal("Active Goal")
    m = _milestone(1, MilestoneStatus.PENDING, title="Research", goal_id=goal.id)
    store = _make_store(goals=[goal], milestones_map={goal.id: [m]})
    config = {"configurable": {"goal_store": store}}
    state = {"prompt": "what should I do?", "session_id": "x"}

    result = await inject_goal_routing_context(state, config)

    assert result["routing_hints"] is not None
    assert "Active Goal" in result["routing_hints"]


async def test_inject_returns_none_on_store_error():
    store = AsyncMock()
    store.list_active = AsyncMock(side_effect=RuntimeError("DB down"))
    config = {"configurable": {"goal_store": store}}
    state = {"prompt": "hello", "session_id": "x"}

    result = await inject_goal_routing_context(state, config)

    assert result == {"routing_hints": None}
