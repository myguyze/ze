from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import asyncpg

from ze_core.logging import get_logger
from ze_personal.workflow.types import StepResult, Workflow, WorkflowExecution, WorkflowStep

log = get_logger(__name__)


def _step_to_dict(step: WorkflowStep) -> dict:
    return {"task": step.task, "agent_hint": step.agent_hint, "verify": step.verify, "intent": step.intent}


def _step_from_dict(d: dict) -> WorkflowStep:
    return WorkflowStep(
        task=d["task"],
        agent_hint=d.get("agent_hint"),
        verify=d.get("verify"),
        intent=d.get("intent", "execute"),
    )


def _step_result_to_dict(r: StepResult) -> dict:
    return {
        "step_index": r.step_index,
        "task": r.task,
        "output": r.output,
        "success": r.success,
        "error": r.error,
        "duration_ms": r.duration_ms,
    }


def _step_result_from_dict(d: dict) -> StepResult:
    return StepResult(
        step_index=d["step_index"],
        task=d["task"],
        output=d.get("output", ""),
        success=d["success"],
        error=d.get("error"),
        duration_ms=d.get("duration_ms", 0),
    )


def _row_to_workflow(row) -> Workflow:
    return Workflow(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        steps=[_step_from_dict(s) for s in row["steps"]],
        schedule=row["schedule"],
        enabled=row["enabled"],
        last_run_at=row["last_run_at"],
        next_run_at=row["next_run_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgresWorkflowStore:
    def __init__(self, db_pool: asyncpg.Pool) -> None:
        self._pool = db_pool

    async def create(self, workflow: Workflow) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workflows (name, description, steps, schedule, enabled, next_run_at)
                VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                RETURNING id
                """,
                workflow.name,
                workflow.description,
                json.dumps([_step_to_dict(s) for s in workflow.steps]),
                workflow.schedule,
                workflow.enabled,
                workflow.next_run_at,
            )
            log.info("workflow_created", name=workflow.name, id=str(row["id"]))
            return row["id"]

    async def get(self, workflow_id: UUID) -> Workflow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflows WHERE id = $1", workflow_id
            )
        return _row_to_workflow(row) if row else None

    async def get_by_name(self, name: str) -> Workflow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflows WHERE name = $1", name
            )
        return _row_to_workflow(row) if row else None

    async def list_all(self) -> list[Workflow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM workflows ORDER BY created_at DESC"
            )
        return [_row_to_workflow(r) for r in rows]

    async def list_enabled_scheduled(self) -> list[Workflow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM workflows"
                " WHERE enabled = TRUE AND schedule IS NOT NULL"
                " ORDER BY name"
            )
        return [_row_to_workflow(r) for r in rows]

    async def set_enabled(self, workflow_id: UUID, enabled: bool) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE workflows SET enabled = $1, updated_at = NOW() WHERE id = $2",
                enabled, workflow_id,
            )

    async def delete(self, workflow_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM workflows WHERE id = $1", workflow_id)
        log.info("workflow_deleted", id=str(workflow_id))

    async def update_run_timestamps(
        self,
        workflow_id: UUID,
        last_run_at: datetime,
        next_run_at: datetime | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflows
                SET last_run_at = $1, next_run_at = $2, updated_at = NOW()
                WHERE id = $3
                """,
                last_run_at, next_run_at, workflow_id,
            )

    async def start_execution(self, workflow_id: UUID | None) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO workflow_executions (workflow_id, status, started_at)
                VALUES ($1, 'running', NOW())
                RETURNING id
                """,
                workflow_id,
            )
            return row["id"]

    async def record_step(self, execution_id: UUID, result: StepResult) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflow_executions
                SET step_results = step_results || $1::jsonb
                WHERE id = $2
                """,
                json.dumps([_step_result_to_dict(result)]),
                execution_id,
            )

    async def finish_execution(
        self,
        execution_id: UUID,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflow_executions
                SET status = $1, error = $2, completed_at = NOW()
                WHERE id = $3
                """,
                status, error, execution_id,
            )

    async def list_executions(self, workflow_id: UUID, limit: int = 20) -> list[WorkflowExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_executions
                WHERE workflow_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                workflow_id, limit,
            )
        return [
            WorkflowExecution(
                id=r["id"],
                workflow_id=r["workflow_id"],
                status=r["status"],
                step_results=[_step_result_from_dict(d) for d in (r["step_results"] or [])],
                error=r["error"],
                started_at=r["started_at"],
                completed_at=r["completed_at"],
                created_at=r["created_at"],
            )
            for r in rows
        ]
