from __future__ import annotations

import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ze_core.errors import GoalPlanError
from ze_personal.goals.planner import GoalPlanner, _parse_plan
from ze_personal.goals.types import Goal, GoalStatus, Milestone, PriorMilestoneOutput


def _goal() -> Goal:
    return Goal(
        id=uuid4(),
        title="Launch a SaaS product",
        objective="Build and launch an MVP",
        success_condition="First paying customer",
        status=GoalStatus.ACTIVE,
    )


def _prior(
    *,
    goal_title="Market Research Goal",
    milestone_title="Survey SaaS competitors",
    output_snippet="Found 12 competitors in the space.",
    completed_days_ago=7,
) -> PriorMilestoneOutput:
    return PriorMilestoneOutput(
        goal_id=uuid4(),
        goal_title=goal_title,
        milestone_id=uuid4(),
        milestone_title=milestone_title,
        output_snippet=output_snippet,
        completed_days_ago=completed_days_ago,
    )


def _plan_json(reuse_hint: str = "") -> str:
    return json.dumps({
        "milestones": [
            {
                "title": "Research market",
                "description": "Survey the market landscape.",
                "agent_hint": "research",
                "intent": "read",
                "sequence": 1,
                "reuse_hint": reuse_hint,
            }
        ],
        "gates": [
            {"after_sequence": 1, "title": "Review research"}
        ],
    })


def _make_planner(response: str) -> GoalPlanner:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)
    return GoalPlanner(client=client, model="test-model")


# ── _parse_plan ───────────────────────────────────────────────────────────────

def test_parse_plan_reads_reuse_hint():
    milestones, _ = _parse_plan(_plan_json(reuse_hint="Prior goal 'X' did this 5 days ago."), uuid4())
    assert milestones[0].reuse_hint == "Prior goal 'X' did this 5 days ago."


def test_parse_plan_defaults_reuse_hint_to_empty_when_absent():
    raw = json.dumps({
        "milestones": [
            {"title": "Step", "description": "Do it", "sequence": 1}
        ],
        "gates": [{"after_sequence": 1, "title": "Check"}],
    })
    milestones, _ = _parse_plan(raw, uuid4())
    assert milestones[0].reuse_hint == ""


def test_parse_plan_truncates_reuse_hint_at_300_chars():
    long_hint = "x" * 500
    milestones, _ = _parse_plan(_plan_json(reuse_hint=long_hint), uuid4())
    assert len(milestones[0].reuse_hint) == 300


def test_parse_plan_handles_null_reuse_hint():
    raw = json.dumps({
        "milestones": [
            {"title": "Step", "description": "Do it", "sequence": 1, "reuse_hint": None}
        ],
        "gates": [{"after_sequence": 1, "title": "Check"}],
    })
    milestones, _ = _parse_plan(raw, uuid4())
    assert milestones[0].reuse_hint == ""


# ── GoalPlanner.plan() ────────────────────────────────────────────────────────

async def test_plan_with_empty_prior_work_sends_unchanged_prompt():
    planner = _make_planner(_plan_json())
    goal = _goal()

    await planner.plan(goal, prior_work=[])

    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert "PRIOR WORK" not in prompt


async def test_plan_with_none_prior_work_sends_unchanged_prompt():
    planner = _make_planner(_plan_json())
    goal = _goal()

    await planner.plan(goal, prior_work=None)

    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert "PRIOR WORK" not in prompt


async def test_plan_with_prior_work_appends_prior_work_block():
    planner = _make_planner(_plan_json())
    goal = _goal()
    pw = _prior()

    await planner.plan(goal, prior_work=[pw])

    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert "PRIOR WORK FROM OTHER GOALS" in prompt
    assert pw.goal_title in prompt
    assert pw.milestone_title in prompt
    assert pw.output_snippet in prompt
    assert f"{pw.completed_days_ago}d ago" in prompt


async def test_plan_returns_milestones_with_reuse_hint():
    hint = "Prior goal 'Market Research' already produced competitor list (7 days ago)."
    planner = _make_planner(_plan_json(reuse_hint=hint))
    goal = _goal()

    milestones, _ = await planner.plan(goal, prior_work=[_prior()])

    assert milestones[0].reuse_hint == hint


# ── GoalPlanner.replan_remaining() ───────────────────────────────────────────

async def test_replan_with_prior_work_appends_prior_work_block():
    planner = _make_planner(_plan_json())
    goal = _goal()
    completed = [
        Milestone(
            id=uuid4(), goal_id=goal.id, title="Done step", description="d",
            sequence=1, status=__import__("ze_personal.goals.types", fromlist=["MilestoneStatus"]).MilestoneStatus.COMPLETED,
            output="Some output",
        )
    ]
    pw = _prior()

    await planner.replan_remaining(goal, completed, "New direction", next_sequence=2, prior_work=[pw])

    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert "PRIOR WORK FROM OTHER GOALS" in prompt
    assert pw.goal_title in prompt


async def test_replan_with_empty_prior_work_omits_prior_work_block():
    planner = _make_planner(_plan_json())
    goal = _goal()

    await planner.replan_remaining(goal, [], "New direction", next_sequence=1, prior_work=[])

    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert "PRIOR WORK" not in prompt


# ── promote_learnings ─────────────────────────────────────────────────────────

import json as _json

from ze_memory.types import Fact
from ze_personal.goals.types import GoalLearning


def _learning(content="User prefers bullet-point summaries.", source="milestone") -> GoalLearning:
    return GoalLearning(goal_id=uuid4(), content=content, source=source)


async def test_promote_learnings_returns_generalizable_facts():
    response = _json.dumps({"facts": [{"key": "output_style", "value": "prefers bullet-point summaries"}]})
    planner = _make_planner(response)
    facts = await planner.promote_learnings(_goal(), [_learning()])
    assert len(facts) == 1
    assert facts[0].predicate == "output_style"
    assert facts[0].value == "prefers bullet-point summaries"


async def test_promote_learnings_sets_agent_and_reviewed():
    response = _json.dumps({"facts": [{"key": "k", "value": "v"}]})
    planner = _make_planner(response)
    facts = await planner.promote_learnings(_goal(), [_learning()])
    assert facts[0].reviewed is False


async def test_promote_learnings_returns_empty_when_no_facts():
    planner = _make_planner(_json.dumps({"facts": []}))
    facts = await planner.promote_learnings(_goal(), [_learning()])
    assert facts == []


async def test_promote_learnings_returns_empty_on_malformed_json():
    planner = _make_planner("not valid json at all")
    facts = await planner.promote_learnings(_goal(), [_learning()])
    assert facts == []


async def test_promote_learnings_caps_at_five_facts():
    many = [{"key": f"k{i}", "value": f"v{i}"} for i in range(8)]
    planner = _make_planner(_json.dumps({"facts": many}))
    facts = await planner.promote_learnings(_goal(), [_learning()])
    assert len(facts) == 5


async def test_promote_learnings_includes_goal_context_in_prompt():
    planner = _make_planner(_json.dumps({"facts": []}))
    goal = _goal()
    await planner.promote_learnings(goal, [_learning(content="Learned X", source="milestone")])
    prompt = planner._client.complete.call_args.kwargs["messages"][0]["content"]
    assert goal.title in prompt
    assert goal.objective in prompt
    assert "Learned X" in prompt
