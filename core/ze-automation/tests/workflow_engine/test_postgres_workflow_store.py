from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_automation.workflow.postgres import PostgresWorkflowStore


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
