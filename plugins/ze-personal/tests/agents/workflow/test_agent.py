from unittest.mock import AsyncMock


from ze_personal.agents.workflow.agent import WorkflowManagerAgent
from ze_agents.types import AgentContext, AgentResult
from ze_agents.types import GateDecision
from ze_sdk.memory import MemoryContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_client(response: str = "Here are your workflows.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(response, None))
    client.complete = AsyncMock(return_value=response)
    return client


def make_ctx(prompt: str = "list my workflows", intent: str = "read") -> AgentContext:
    return AgentContext(
        session_id="test",
        prompt=prompt,
        intent=intent,
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(client=None) -> WorkflowManagerAgent:
    return WorkflowManagerAgent(
        openrouter_client=client or make_client(),
        workflow_store=AsyncMock(),
        workflow_planner=AsyncMock(),
        workflow_scheduler=AsyncMock(),
    )


# ── Registry ──────────────────────────────────────────────────────────────────

def test_workflow_agent_is_registered():
    from ze_agents.registry import _registry
    assert "workflow" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "workflow"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("You have 2 workflows: daily-digest, weekly-report.")
    result = await make_agent(client=client).run(make_ctx())
    assert result.response == "You have 2 workflows: daily-digest, weekly-report."


# ── run() — tool call round-trips ────────────────────────────────────────────

async def test_run_lists_workflows_via_tool():

    from ze_personal.workflow.types import Workflow, WorkflowStep
    from uuid import uuid4
    from datetime import datetime

    store = AsyncMock()
    store.list_all = AsyncMock(return_value=[
        Workflow(
            id=uuid4(), name="daily-digest", description="Send a daily summary",
            steps=[WorkflowStep(task="Fetch news")], schedule="0 8 * * *",
            enabled=True, last_run_at=None, next_run_at=None,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
    ])

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_workflows", "arguments": {}}]),
        ("You have 1 workflow: daily-digest.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = WorkflowManagerAgent(
        openrouter_client=client,
        workflow_store=store,
        workflow_planner=AsyncMock(),
        workflow_scheduler=AsyncMock(),
    )
    result = await agent.run(make_ctx())

    store.list_all.assert_called_once()
    assert result.response == "You have 1 workflow: daily-digest."
    assert len([tc for tc in result.tool_calls if tc.tool_name == "list_workflows"]) == 1


async def test_run_creates_workflow_via_tool():
    import ze_personal.agents.workflow.tools  # noqa

    from uuid import uuid4

    store = AsyncMock()
    store.create = AsyncMock(return_value=uuid4())
    store.get_by_name = AsyncMock(return_value=None)

    from ze_personal.workflow.types import WorkflowStep
    planner = AsyncMock()
    planner.plan = AsyncMock(return_value=[WorkflowStep(task="Fetch headlines")])
    planner.extract_schedule = AsyncMock(return_value="0 8 * * *")

    scheduler = AsyncMock()
    scheduler.add_workflow = AsyncMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "create_workflow", "arguments": {
            "workflow_name": "morning-digest",
            "description": "Fetch headlines and email a summary",
            "schedule_description": "every day at 8am",
        }}]),
        ("Created workflow morning-digest with 1 step, runs daily at 8am.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = WorkflowManagerAgent(
        openrouter_client=client,
        workflow_store=store,
        workflow_planner=planner,
        workflow_scheduler=scheduler,
    )
    result = await agent.run(make_ctx("create a morning digest workflow", intent="manage"))

    store.create.assert_called_once()
    scheduler.add_workflow.assert_called_once()
    assert "morning-digest" in result.response


async def test_run_trigger_workflow_via_tool():
    import ze_personal.agents.workflow.tools  # noqa

    from uuid import uuid4
    from datetime import datetime
    from ze_personal.workflow.types import Workflow

    wf = Workflow(
        id=uuid4(), name="daily-digest", description="desc",
        steps=[], schedule=None, enabled=True,
        last_run_at=None, next_run_at=None,
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=wf)
    scheduler = AsyncMock()
    scheduler.trigger_now = AsyncMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "trigger_workflow", "arguments": {"workflow_name": "daily-digest"}}]),
        ("Triggered daily-digest.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = WorkflowManagerAgent(
        openrouter_client=client,
        workflow_store=store,
        workflow_planner=AsyncMock(),
        workflow_scheduler=scheduler,
    )
    result = await agent.run(make_ctx("run daily-digest now", intent="manage"))

    scheduler.trigger_now.assert_called_once_with(wf.id)
    assert result.response == "Triggered daily-digest."


async def test_run_no_tool_calls_when_llm_answers_directly():
    result = await make_agent().run(make_ctx())
    assert len(result.tool_calls) == 0


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_response():
    client = make_client("Workflows: daily-digest.")
    tokens = [t async for t in make_agent(client=client).stream(make_ctx())]
    assert "".join(tokens) == "Workflows: daily-digest."
