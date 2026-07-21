from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_automation.workflow.postgres import (
    PostgresWorkflowStore,
    _step_from_dict,
    _step_result_from_dict,
    _step_result_to_dict,
    _step_to_dict,
)
from ze_automation.workflow.types import StepResult, WorkflowStep


def _make_pool(fetchrow=None, fetch=None, execute=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(side_effect=fetchrow if callable(fetchrow) else None)
    if not callable(fetchrow):
        conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.fetch = AsyncMock(return_value=fetch or [])
    conn.execute = AsyncMock(return_value=execute)

    @asynccontextmanager
    async def transaction():
        yield

    conn.transaction = transaction

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


def test_step_round_trip_on_failure():
    step = WorkflowStep(task="monitor", id="s0", on_failure="continue")
    data = _step_to_dict(step)
    assert "on_failure" in data
    restored = _step_from_dict(data, 0)
    assert restored.on_failure == "continue"


def test_step_from_dict_defaults_on_failure_to_fail():
    restored = _step_from_dict({"task": "x", "id": "s0"}, 0)
    assert restored.on_failure == "fail"


def test_step_result_round_trip_new_fields():
    result = StepResult(
        step_index=0,
        task="monitor",
        output="nothing new",
        success=True,
        error=None,
        duration_ms=100,
        step_id="s0",
        attempt_count=2,
        no_results=True,
    )
    data = _step_result_to_dict(result)
    assert data["attempt_count"] == 2
    assert data["no_results"] is True
    restored = _step_result_from_dict(data)
    assert restored.attempt_count == 2
    assert restored.no_results is True


def test_step_result_from_dict_defaults():
    restored = _step_result_from_dict(
        {
            "step_index": 0,
            "task": "x",
            "success": True,
            "error": None,
            "duration_ms": 0,
        }
    )
    assert restored.attempt_count == 1
    assert restored.no_results is False


async def test_start_execution_persists_steps_snapshot():
    workflow_id = uuid4()
    execution_id = uuid4()
    steps_json = [
        {"task": "First", "id": "s0", "on_failure": "continue"},
        {"task": "Second", "id": "s1"},
    ]
    expected_snapshot = [
        _step_to_dict(_step_from_dict(steps_json[0], 0)),
        _step_to_dict(_step_from_dict(steps_json[1], 1)),
    ]
    captured: dict[str, object] = {}

    async def fetchrow_side_effect(query, *args):
        if "SELECT steps FROM workflows" in query:
            return {"steps": steps_json}
        if "INSERT INTO workflow_executions" in query:
            captured["workflow_id"] = args[0]
            captured["snapshot"] = args[1]
            return {"id": execution_id}
        return None

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    store = PostgresWorkflowStore(pool)

    result = await store.start_execution(workflow_id)

    assert result == execution_id
    assert captured["workflow_id"] == workflow_id
    assert captured["snapshot"] == expected_snapshot
    assert conn.fetchrow.await_count == 2


async def test_update_steps_does_not_touch_execution_snapshots():
    workflow_id = uuid4()

    async def fetchrow_side_effect(query, *args):
        if "SELECT steps FROM workflows" in query:
            return {"steps": []}
        if "revision_number" in query:
            return {"next": 1}
        return None

    pool, conn = _make_pool()
    conn.fetchrow = AsyncMock(side_effect=fetchrow_side_effect)
    store = PostgresWorkflowStore(pool)
    new_steps = [
        WorkflowStep(task="Updated", id="s0"),
        WorkflowStep(task="Added", id="s1"),
    ]

    await store.update_steps(workflow_id, new_steps)

    update_query = conn.execute.call_args_list[0].args[0]
    assert "UPDATE workflows" in update_query
    for call in conn.execute.call_args_list:
        assert "workflow_executions" not in call.args[0]
