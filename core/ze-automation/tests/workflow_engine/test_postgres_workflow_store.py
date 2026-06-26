from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_automation.workflow.postgres import (
    PostgresWorkflowStore,
    _coerce_jsonb_list,
    _row_to_workflow,
)
from ze_automation.workflow.types import WorkflowStep


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
    )
