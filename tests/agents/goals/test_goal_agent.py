import json
import pathlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.agents.goals.agent import GoalAgent
from ze.agents.types import AgentContext
from ze.goals.types import Goal, GoalStatus, Milestone, MilestoneStatus
from ze.logging import configure_logging


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    from ze.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_agent(llm_response: str = ""):
    client = MagicMock()
    client.complete = AsyncMock(return_value=llm_response)

    goal_store = MagicMock()
    goal_store.create_goal = AsyncMock(return_value=Goal(
        id=uuid4(), title="T", objective="O", success_condition="S",
    ))
    goal_store.list_all = AsyncMock(return_value=[])
    goal_store.list_active = AsyncMock(return_value=[])
    goal_store.get_goal = AsyncMock(return_value=None)
    goal_store.update_status = AsyncMock()
    goal_store.create_milestone = AsyncMock()
    goal_store.create_gate = AsyncMock()
    goal_store.list_milestones = AsyncMock(return_value=[])
    goal_store.list_learnings = AsyncMock(return_value=[])
    goal_store.get_pending_gate = AsyncMock(return_value=None)

    goal_planner = MagicMock()
    goal_planner.plan = AsyncMock(return_value=([], []))

    notifier = MagicMock()
    notifier.push_with_keyboard = AsyncMock()

    return GoalAgent(
        openrouter_client=client,
        goal_store=goal_store,
        goal_planner=goal_planner,
        notifier=notifier,
        settings=make_settings(),
    ), goal_store, goal_planner, notifier


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


def make_ctx(prompt: str = "Create a goal") -> AgentContext:
    return AgentContext(session_id="test", prompt=prompt, intent="create")


# ── list ──────────────────────────────────────────────────────────────────────

async def test_list_returns_no_goals_message():
    agent, store, _, _ = make_agent(json.dumps({"action": "list"}))
    store.list_all = AsyncMock(return_value=[])
    result = await agent.run(make_ctx("list goals"))
    assert "No goals" in result.response


async def test_list_returns_goals():
    goals = [
        Goal(id=uuid4(), title="G1", objective="obj1", success_condition="done", status=GoalStatus.ACTIVE),
    ]
    agent, store, _, _ = make_agent(json.dumps({"action": "list"}))
    store.list_all = AsyncMock(return_value=goals)
    result = await agent.run(make_ctx())
    assert "G1" in result.response


# ── create ────────────────────────────────────────────────────────────────────

async def test_create_calls_planner_and_store():
    cmd = json.dumps({
        "action": "create",
        "title": "Find leads",
        "objective": "Build a list",
        "success_condition": "20 contacts",
        "time_horizon": "2 weeks",
        "type": "outreach",
    })
    agent, store, planner, notifier = make_agent(cmd)

    m = MagicMock()
    m.goal_id = uuid4()
    m.sequence = 1
    m.title = "Step 1"
    planner.plan = AsyncMock(return_value=([m], []))

    result = await agent.run(make_ctx())
    planner.plan.assert_awaited_once()
    store.create_goal.assert_awaited_once()
    store.update_status.assert_not_called()
    notifier.push_with_keyboard.assert_awaited_once()
    assert "Find leads" in result.response
    assert "Approve" in result.response


async def test_create_returns_error_without_required_fields():
    cmd = json.dumps({"action": "create", "title": None, "objective": None, "success_condition": None})
    agent, _, _, _ = make_agent(cmd)
    result = await agent.run(make_ctx())
    assert "Please provide" in result.response


# ── status ────────────────────────────────────────────────────────────────────

async def test_status_returns_not_found_for_missing_goal():
    gid = uuid4()
    cmd = json.dumps({"action": "status", "goal_id": str(gid)})
    agent, store, _, _ = make_agent(cmd)
    store.get_goal = AsyncMock(return_value=None)
    result = await agent.run(make_ctx())
    assert "not found" in result.response.lower()


async def test_status_returns_goal_info():
    goal = Goal(id=uuid4(), title="My Goal", objective="o", success_condition="s", status=GoalStatus.ACTIVE)
    cmd = json.dumps({"action": "status", "goal_id": str(goal.id)})
    agent, store, _, _ = make_agent(cmd)
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    result = await agent.run(make_ctx())
    assert "My Goal" in result.response


# ── invalid JSON ──────────────────────────────────────────────────────────────

async def test_run_returns_error_on_invalid_json():
    agent, _, _, _ = make_agent("not json")
    result = await agent.run(make_ctx())
    assert "couldn't understand" in result.response.lower()
