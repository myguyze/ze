"""Tests for GET /api/v0/workflows/{id} and /api/v0/workflows/{id}/executions."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from ze_api.api.dependencies import require_api_key
from ze_api.api.routes.workflows import router
from ze_automation.workflow.types import (
    Branch,
    StepResult,
    Workflow,
    WorkflowExecution,
    WorkflowStep,
)

API_KEY = "test-key"


def _workflow(steps: list[WorkflowStep]) -> Workflow:
    now = datetime.now(timezone.utc)
    return Workflow(
        id=uuid4(),
        name="Branching workflow",
        description="A workflow with branches",
        steps=steps,
        schedule=None,
        enabled=True,
        last_run_at=None,
        next_run_at=None,
        created_at=now,
        updated_at=now,
    )


def _make_app(
    workflow: Workflow, executions: list[WorkflowExecution] | None = None
) -> FastAPI:
    app = FastAPI()

    workflow_store = AsyncMock()
    workflow_store.get = AsyncMock(return_value=workflow)
    workflow_store.list_executions = AsyncMock(return_value=executions or [])
    workflow_store.get_execution = AsyncMock(
        return_value=executions[0] if executions else None
    )
    workflow_store.list_all = AsyncMock(return_value=[workflow])

    container = SimpleNamespace(
        workflow_store=workflow_store,
        workflow_scheduler=AsyncMock(),
    )
    app.state.container = container

    app.dependency_overrides[require_api_key] = lambda: None
    app.include_router(router, prefix="/api/v0/workflows")
    return app


@pytest.mark.asyncio
async def test_get_workflow_includes_branch_fields():
    steps = [
        WorkflowStep(
            task="Check status",
            id="s0",
            branches=[
                Branch(condition="ok", to="s1"),
                Branch(condition="fail", to="FAIL"),
            ],
            default_next="s1",
        ),
        WorkflowStep(task="Notify", id="s1"),
    ]
    workflow = _workflow(steps)
    app = _make_app(workflow)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/workflows/{workflow.id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    step0 = data["steps"][0]
    assert step0["id"] == "s0"
    assert step0["default_next"] == "s1"
    assert step0["branches"] == [
        {"condition": "ok", "to": "s1"},
        {"condition": "fail", "to": "FAIL"},
    ]
    step1 = data["steps"][1]
    assert step1["id"] == "s1"
    assert step1["branches"] == []
    assert step1["default_next"] is None


@pytest.mark.asyncio
async def test_list_workflow_executions_includes_step_id_and_branch_taken():
    workflow = _workflow([WorkflowStep(task="Check status", id="s0")])
    execution = WorkflowExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        status="completed",
        step_results=[
            StepResult(
                step_index=0,
                task="Check status",
                output="ok",
                success=True,
                error=None,
                duration_ms=10,
                step_id="s0",
                branch_taken="ok",
            )
        ],
        created_at=datetime.now(timezone.utc),
    )
    app = _make_app(workflow, executions=[execution])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/workflows/{workflow.id}/executions",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    result = data[0]["step_results"][0]
    assert result["step_id"] == "s0"
    assert result["branch_taken"] == "ok"


@pytest.mark.asyncio
async def test_get_workflow_execution_includes_steps_snapshot():
    workflow = _workflow(
        [
            WorkflowStep(task="Original step", id="s0"),
            WorkflowStep(task="Second step", id="s1"),
        ]
    )
    execution = WorkflowExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        status="completed",
        step_results=[],
        steps_snapshot=[WorkflowStep(task="Original step", id="s0")],
        created_at=datetime.now(timezone.utc),
    )
    app = _make_app(workflow, executions=[execution])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/workflows/{workflow.id}/executions/{execution.id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps_snapshot"]) == 1
    assert data["steps_snapshot"][0]["task"] == "Original step"
    assert data["steps_snapshot"][0]["id"] == "s0"


@pytest.mark.asyncio
async def test_get_workflow_execution_by_id():
    workflow = _workflow([WorkflowStep(task="Check status", id="s0")])
    execution = WorkflowExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        status="running",
        step_results=[],
        created_at=datetime.now(timezone.utc),
    )
    app = _make_app(workflow, executions=[execution])

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/v0/workflows/{workflow.id}/executions/{execution.id}",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["id"] == str(execution.id)
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_update_workflow_steps_success():
    steps = [
        WorkflowStep(task="Check status", id="s0", on_failure="continue"),
        WorkflowStep(task="Notify", id="s1"),
    ]
    workflow = _workflow(steps)
    app = _make_app(workflow)
    app.state.container.workflow_store.update_steps = AsyncMock()
    app.state.container.workflow_store.get = AsyncMock(return_value=workflow)

    payload = {
        "steps": [
            {
                "id": "s0",
                "task": "Check status",
                "on_failure": "continue",
                "branches": [],
            },
            {"id": "s1", "task": "Notify", "branches": []},
        ]
    }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            f"/api/v0/workflows/{workflow.id}/steps",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
        )

    assert resp.status_code == 200
    assert resp.json()["steps"][0]["on_failure"] == "continue"


@pytest.mark.asyncio
async def test_update_workflow_steps_validation_error():
    workflow = _workflow([WorkflowStep(task="Check status", id="s0")])
    app = _make_app(workflow)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.patch(
            f"/api/v0/workflows/{workflow.id}/steps",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={
                "steps": [
                    {
                        "id": "s0",
                        "task": "Check status",
                        "branches": [{"condition": "x", "to": "missing"}],
                    }
                ]
            },
        )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_cancel_workflow_execution_running():
    workflow = _workflow([WorkflowStep(task="Check status", id="s0")])
    execution = WorkflowExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        status="running",
        step_results=[],
        created_at=datetime.now(timezone.utc),
    )
    app = _make_app(workflow, executions=[execution])
    scheduler = AsyncMock()
    scheduler.cancel_execution = AsyncMock(return_value="cancelled")
    app.state.container.workflow_scheduler = scheduler

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v0/workflows/{workflow.id}/executions/{execution.id}/cancel",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_workflow_execution_not_running():
    workflow = _workflow([WorkflowStep(task="Check status", id="s0")])
    execution = WorkflowExecution(
        id=uuid4(),
        workflow_id=workflow.id,
        status="completed",
        step_results=[],
        created_at=datetime.now(timezone.utc),
    )
    app = _make_app(workflow, executions=[execution])
    scheduler = AsyncMock()
    scheduler.cancel_execution = AsyncMock(return_value="not_running")
    app.state.container.workflow_scheduler = scheduler

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            f"/api/v0/workflows/{workflow.id}/executions/{execution.id}/cancel",
            headers={"Authorization": f"Bearer {API_KEY}"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "not_running"
