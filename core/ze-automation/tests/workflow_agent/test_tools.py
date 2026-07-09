from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import ze_automation.agents.workflow.tools as tools
from ze_automation.workflow.types import Branch, StepResult, Workflow, WorkflowExecution, WorkflowStep


def _workflow(name: str = "trump-health") -> Workflow:
    now = datetime.now(tz=timezone.utc)
    return Workflow(
        id=uuid4(),
        name=name,
        description="Track Trump health news",
        steps=[WorkflowStep(task="Search recent headlines")],
        schedule="0 8 * * *",
        enabled=True,
        last_run_at=now,
        next_run_at=None,
        created_at=now,
        updated_at=now,
    )


def _execution(status: str = "completed") -> WorkflowExecution:
    now = datetime.now(tz=timezone.utc)
    return WorkflowExecution(
        id=uuid4(),
        workflow_id=uuid4(),
        status=status,
        step_results=[
            StepResult(
                step_index=0,
                task="Search recent headlines",
                output="No major developments today.",
                success=True,
                error=None,
                duration_ms=1200,
            )
        ],
        error=None,
        summary="No major Trump health developments today.",
        started_at=now,
        completed_at=now,
        created_at=now,
    )


async def test_get_workflow_includes_last_execution():
    wf = _workflow()
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=wf)
    store.list_executions = AsyncMock(return_value=[_execution()])

    result = await tools.get_workflow(store, "trump-health")

    store.list_executions.assert_called_once_with(wf.id, limit=1)
    assert result["name"] == "trump-health"
    assert result["last_execution"]["status"] == "completed"
    assert result["last_execution"]["summary"] == "No major Trump health developments today."
    assert result["last_execution"]["step_results"][0]["success"] is True


async def test_get_workflow_without_executions():
    wf = _workflow()
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=wf)
    store.list_executions = AsyncMock(return_value=[])

    result = await tools.get_workflow(store, "trump-health")

    assert result["last_execution"] is None


async def test_list_workflow_executions_returns_history():
    wf = _workflow()
    failed = _execution(status="failed")
    failed.error = "News agent timed out"
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=wf)
    store.list_executions = AsyncMock(return_value=[failed, _execution()])

    result = await tools.list_workflow_executions(store, "trump-health", limit=3)

    store.list_executions.assert_called_once_with(wf.id, limit=3)
    assert result["workflow_name"] == "trump-health"
    assert len(result["executions"]) == 2
    assert result["executions"][0]["status"] == "failed"
    assert result["executions"][0]["error"] == "News agent timed out"


async def test_list_workflow_executions_unknown_workflow():
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=None)

    result = await tools.list_workflow_executions(store, "missing")

    assert "error" in result


async def test_create_workflow_rejects_invalid_branch_target():
    store = AsyncMock()
    scheduler = AsyncMock()
    planner = MagicMock()
    planner.plan = AsyncMock(return_value=[
        WorkflowStep(task="Check invoice", id="s0", branches=[Branch(condition="invoice found", to="s9")]),
    ])
    planner.extract_schedule = AsyncMock()

    result = await tools.create_workflow(store, planner, scheduler, "invoice-check", "Check for invoices")

    assert result == {"error": "Couldn't plan the workflow: step 's0' branches to unknown step 's9'"}
    store.create.assert_not_called()
    planner.extract_schedule.assert_not_called()


def _legacy_workflow(name: str = "morning-briefing") -> Workflow:
    now = datetime.now(tz=timezone.utc)
    return Workflow(
        id=uuid4(),
        name=name,
        description="Legacy stored workflow",
        steps=[
            WorkflowStep(task="Fetch news", agent_hint="news", intent="read", id="s0"),
            WorkflowStep(task="Summarize", intent="reason", id="s1"),
        ],
        schedule="0 8 * * *",
        enabled=True,
        last_run_at=None,
        next_run_at=None,
        created_at=now,
        updated_at=now,
    )


def _linear_workflow(name: str = "morning-briefing-new") -> Workflow:
    now = datetime.now(tz=timezone.utc)
    return Workflow(
        id=uuid4(),
        name=name,
        description="Newly authored linear workflow",
        steps=[
            WorkflowStep(task="Fetch news", agent_hint="news", intent="read", id="s0"),
            WorkflowStep(task="Summarize", intent="reason", id="s1"),
        ],
        schedule=None,
        enabled=True,
        last_run_at=None,
        next_run_at=None,
        created_at=now,
        updated_at=now,
    )


async def test_get_workflow_returns_legacy_steps_with_backfilled_branch_fields():
    legacy = _legacy_workflow()
    linear = _linear_workflow()
    store = AsyncMock()
    store.get_by_name = AsyncMock(side_effect=[legacy, linear])
    store.list_executions = AsyncMock(return_value=[])

    legacy_result = await tools.get_workflow(store, "morning-briefing")
    linear_result = await tools.get_workflow(store, "morning-briefing-new")

    assert legacy_result["steps"] == [
        {
            "task": "Fetch news",
            "agent_hint": "news",
            "intent": "read",
            "id": "s0",
            "branches": [],
            "default_next": None,
        },
        {
            "task": "Summarize",
            "agent_hint": None,
            "intent": "reason",
            "id": "s1",
            "branches": [],
            "default_next": None,
        },
    ]
    assert legacy_result["steps"] == linear_result["steps"]


async def test_list_workflows_includes_legacy_workflow_metadata():
    legacy = _legacy_workflow()
    store = AsyncMock()
    store.list_all = AsyncMock(return_value=[legacy])

    result = await tools.list_workflows(store)

    assert len(result) == 1
    assert result[0]["name"] == "morning-briefing"
    assert result[0]["enabled"] is True
