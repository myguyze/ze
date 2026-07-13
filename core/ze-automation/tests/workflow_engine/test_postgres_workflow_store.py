from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_automation.workflow.postgres import (
    PostgresWorkflowStore,
    _coerce_jsonb_list,
    _row_to_workflow,
    _step_from_dict,
    _step_result_from_dict,
    _step_result_to_dict,
    _step_to_dict,
)
from ze_automation.workflow.types import Branch, StepResult, WorkflowStep


def _make_pool():
    conn = AsyncMock()
    conn.execute = AsyncMock()

    @asynccontextmanager
    async def acquire():
        yield conn

    pool = MagicMock()
    pool.acquire = acquire
    return pool, conn


async def test_update_schedule_writes_cron_and_next_run():
    pool, conn = _make_pool()
    store = PostgresWorkflowStore(pool)
    workflow_id = uuid4()

    await store.update_schedule(workflow_id, "0 9 * * 1", None)

    conn.execute.assert_called_once()
    sql, schedule, next_run, wf_id = conn.execute.call_args.args
    assert "UPDATE workflows" in sql
    assert "schedule = $1" in sql
    assert schedule == "0 9 * * 1"
    assert next_run is None
    assert wf_id == workflow_id


async def test_update_schedule_clears_schedule():
    pool, conn = _make_pool()
    store = PostgresWorkflowStore(pool)
    workflow_id = uuid4()

    await store.update_schedule(workflow_id, None, None)

    _, schedule, next_run, _ = conn.execute.call_args.args
    assert schedule is None
    assert next_run is None


def test_coerce_jsonb_list_parses_double_encoded_string():
    raw = '[{"task": "Send reminder", "intent": "execute"}]'
    assert _coerce_jsonb_list(raw) == [{"task": "Send reminder", "intent": "execute"}]


def test_row_to_workflow_accepts_string_steps():
    from datetime import datetime, timezone

    row = {
        "id": uuid4(),
        "name": "Morning briefing",
        "description": "Daily briefing",
        "steps": '[{"task": "Fetch news", "agent_hint": "news", "intent": "execute"}]',
        "schedule": "0 8 * * *",
        "enabled": True,
        "last_run_at": None,
        "next_run_at": None,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }

    workflow = _row_to_workflow(row)

    assert len(workflow.steps) == 1
    assert workflow.steps[0] == WorkflowStep(
        task="Fetch news",
        agent_hint="news",
        intent="execute",
        id="s0",
    )


def test_row_to_workflow_backfills_ids_in_list_order():
    from datetime import datetime, timezone

    row = {
        "id": uuid4(),
        "name": "Legacy workflow",
        "description": "Pre-existing, no ids",
        "steps": [
            {"task": "Fetch news", "intent": "read"},
            {"task": "Summarize", "intent": "reason"},
            {"task": "Send digest", "intent": "execute"},
        ],
        "schedule": None,
        "enabled": True,
        "last_run_at": None,
        "next_run_at": None,
        "created_at": datetime.now(tz=timezone.utc),
        "updated_at": datetime.now(tz=timezone.utc),
    }

    workflow = _row_to_workflow(row)

    assert [s.id for s in workflow.steps] == ["s0", "s1", "s2"]
    assert all(s.branches == [] for s in workflow.steps)
    assert all(s.default_next is None for s in workflow.steps)


def test_step_to_dict_and_from_dict_round_trip_branches_and_default_next():
    step = WorkflowStep(
        task="Check invoice",
        agent_hint="finance",
        verify="an invoice was found",
        intent="read",
        id="s1",
        branches=[
            Branch(condition="invoice found", to="s2"),
            Branch(condition="no invoice", to="END"),
        ],
        default_next="s3",
    )

    d = _step_to_dict(step)
    restored = _step_from_dict(d, index=0)

    assert restored == step


def test_step_from_dict_backfills_id_when_absent():
    d = {"task": "Fetch news", "agent_hint": "news", "intent": "execute"}

    restored = _step_from_dict(d, index=4)

    assert restored.id == "s4"
    assert restored.branches == []
    assert restored.default_next is None


def test_step_result_to_dict_and_from_dict_round_trip_step_id_and_branch_taken():
    result = StepResult(
        step_index=1,
        task="Check invoice",
        output="found",
        success=True,
        error=None,
        duration_ms=42,
        step_id="s1",
        branch_taken="invoice found",
    )

    d = _step_result_to_dict(result)
    restored = _step_result_from_dict(d)

    assert restored == result


def test_step_result_from_dict_defaults_step_id_and_branch_taken_when_absent():
    d = {
        "step_index": 0,
        "task": "Legacy step",
        "output": "done",
        "success": True,
        "error": None,
        "duration_ms": 5,
    }

    restored = _step_result_from_dict(d)

    assert restored.step_id == ""
    assert restored.branch_taken is None
