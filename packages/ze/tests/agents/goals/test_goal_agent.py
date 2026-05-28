import pathlib
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.agents.goals.agent import GoalAgent
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.capability.types import GateDecision
from ze_core.goals.types import Goal, GoalStatus, Milestone, MilestoneStatus
from ze_core.memory.types import MemoryContext
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


def make_client(response: str = "Here are your goals.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(response, None))
    client.complete = AsyncMock(return_value=response)
    return client


def make_ctx(prompt: str = "list my goals", intent: str = "read") -> AgentContext:
    return AgentContext(
        session_id="test",
        prompt=prompt,
        intent=intent,
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_store() -> MagicMock:
    store = MagicMock()
    store.list_all = AsyncMock(return_value=[])
    store.list_active = AsyncMock(return_value=[])
    store.get_goal = AsyncMock(return_value=None)
    store.update_status = AsyncMock()
    store.create_goal = AsyncMock()
    store.create_milestone = AsyncMock()
    store.create_gate = AsyncMock()
    store.list_milestones = AsyncMock(return_value=[])
    store.list_learnings = AsyncMock(return_value=[])
    store.get_pending_gate = AsyncMock(return_value=None)
    return store


def make_agent(client=None, store=None) -> GoalAgent:
    return GoalAgent(
        openrouter_client=client or make_client(),
        goal_store=store or make_store(),
        goal_planner=AsyncMock(),
        goal_executor=AsyncMock(),
        notifier=AsyncMock(),
        settings=make_settings(),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registry ──────────────────────────────────────────────────────────────────

def test_goal_agent_is_registered():
    from ze_core.orchestration.registry import _registry
    assert "goals" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "goals"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("You have 2 active goals.")
    result = await make_agent(client=client).run(make_ctx())
    assert result.response == "You have 2 active goals."


# ── run() — tool call round-trips ────────────────────────────────────────────

async def test_run_lists_goals_via_tool():
    import ze.agents.goals.tools  # noqa: ensure tools registered

    gid = uuid4()
    store = make_store()
    store.list_all = AsyncMock(return_value=[
        Goal(id=gid, title="Find leads", objective="Build a list of 20 contacts",
             success_condition="20 contacts", status=GoalStatus.ACTIVE),
    ])

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_goals", "arguments": {}}]),
        ("You have 1 active goal: Find leads.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    result = await make_agent(client=client, store=store).run(make_ctx())

    store.list_all.assert_called_once()
    assert "Find leads" in result.response
    assert len([tc for tc in result.tool_calls if tc.tool_name == "list_goals"]) == 1


async def test_run_gets_goal_status_via_tool():
    import ze.agents.goals.tools  # noqa

    gid = uuid4()
    goal = Goal(id=gid, title="My Goal", objective="o", success_condition="s", status=GoalStatus.ACTIVE)
    store = make_store()
    store.get_goal = AsyncMock(return_value=goal)
    store.list_milestones = AsyncMock(return_value=[
        Milestone(id=uuid4(), goal_id=gid, title="Step 1", description="d", sequence=1,
                  status=MilestoneStatus.COMPLETED),
    ])

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "get_goal_status", "arguments": {"goal_id": str(gid)}}]),
        ("My Goal is active — 1/1 milestones done.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    result = await make_agent(client=client, store=store).run(make_ctx("status of my goal"))

    store.get_goal.assert_called_once_with(gid)
    assert "My Goal" in result.response


async def test_run_creates_goal_via_tool():
    import ze.agents.goals.tools  # noqa

    gid = uuid4()
    created_goal = Goal(id=gid, title="Find leads", objective="Build a list",
                        success_condition="20 contacts", status=GoalStatus.PLANNING)

    planner = AsyncMock()
    m = MagicMock()
    m.goal_id = gid
    m.sequence = 1
    m.title = "Research targets"
    planner.plan = AsyncMock(return_value=([m], []))

    store = make_store()
    store.create_goal = AsyncMock(return_value=created_goal)

    notifier = AsyncMock()
    notifier.push_notification = AsyncMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "create_goal", "arguments": {
            "goal_title": "Find leads",
            "objective": "Build a list of 20 contacts",
            "success_condition": "20 qualified contacts in CRM",
            "time_horizon": "2 weeks",
            "goal_type": "outreach",
        }}]),
        ("Goal 'Find leads' planned with 1 milestone. Approve in Telegram to start.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = GoalAgent(
        openrouter_client=client,
        goal_store=store,
        goal_planner=planner,
        goal_executor=AsyncMock(),
        notifier=notifier,
        settings=make_settings(),
    )
    result = await agent.run(make_ctx("create a goal to find 20 leads in 2 weeks", intent="create"))

    store.create_goal.assert_called_once()
    store.create_milestone.assert_called_once()
    notifier.push_notification.assert_called_once()
    assert "Find leads" in result.response


async def test_run_pauses_goal_via_tool():
    import ze.agents.goals.tools  # noqa

    gid = uuid4()
    goal = Goal(id=gid, title="My Goal", objective="o", success_condition="s", status=GoalStatus.ACTIVE)
    store = make_store()
    store.get_goal = AsyncMock(return_value=goal)

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "pause_goal", "arguments": {"goal_id": str(gid)}}]),
        ("Paused goal 'My Goal'.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    result = await make_agent(client=client, store=store).run(
        make_ctx("pause my goal", intent="update")
    )

    store.update_status.assert_called_once_with(gid, GoalStatus.PAUSED)
    assert result.response


async def test_run_resumes_goal_via_tool():
    import ze.agents.goals.tools  # noqa

    gid = uuid4()
    goal = Goal(id=gid, title="My Goal", objective="o", success_condition="s", status=GoalStatus.PAUSED)
    store = make_store()
    store.get_goal = AsyncMock(return_value=goal)
    executor = AsyncMock()
    executor.advance = AsyncMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "resume_goal", "arguments": {"goal_id": str(gid)}}]),
        ("Resumed goal 'My Goal'.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = GoalAgent(
        openrouter_client=client,
        goal_store=store,
        goal_planner=AsyncMock(),
        goal_executor=executor,
        notifier=AsyncMock(),
        settings=make_settings(),
    )
    result = await agent.run(make_ctx("resume my goal", intent="update"))

    store.update_status.assert_called_once_with(gid, GoalStatus.ACTIVE)
    assert result.response


async def test_run_abandons_goal_via_tool():
    import ze.agents.goals.tools  # noqa

    gid = uuid4()
    goal = Goal(id=gid, title="My Goal", objective="o", success_condition="s", status=GoalStatus.ACTIVE)
    store = make_store()
    store.get_goal = AsyncMock(return_value=goal)

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "abandon_goal", "arguments": {"goal_id": str(gid)}}]),
        ("Abandoned goal 'My Goal'.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    result = await make_agent(client=client, store=store).run(
        make_ctx("abandon my goal", intent="delete")
    )

    store.update_status.assert_called_once_with(gid, GoalStatus.ABANDONED)
    assert result.response


async def test_run_no_tool_calls_when_llm_answers_directly():
    result = await make_agent().run(make_ctx())
    assert len(result.tool_calls) == 0


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_response():
    client = make_client("Goals: Find leads.")
    tokens = [t async for t in make_agent(client=client).stream(make_ctx())]
    assert "".join(tokens) == "Goals: Find leads."
