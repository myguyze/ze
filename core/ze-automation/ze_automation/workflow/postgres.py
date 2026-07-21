from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import asyncpg

from ze_agents.errors import WorkflowPlanError
from ze_logging import get_logger
from ze_automation.workflow.revision_summary import build_change_summary
from ze_automation.workflow.types import (
    ActorContext,
    ActorSource,
    Branch,
    StepResult,
    Workflow,
    WorkflowExecution,
    WorkflowRevision,
    WorkflowStep,
)
from ze_automation.workflow.validation import validate_workflow_steps

log = get_logger(__name__)


def _step_to_dict(step: WorkflowStep) -> dict:
    data = {
        "task": step.task,
        "agent_hint": step.agent_hint,
        "verify": step.verify,
        "intent": step.intent,
        "id": step.id,
        "branches": [{"condition": b.condition, "to": b.to} for b in step.branches],
        "default_next": step.default_next,
    }
    if step.on_failure != "fail":
        data["on_failure"] = step.on_failure
    return data


def _coerce_jsonb_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, str):
            parsed = json.loads(parsed)
        if isinstance(parsed, list):
            return parsed
        return [parsed]
    if isinstance(value, list):
        return value
    return list(value)


def _step_from_dict(d: dict | str, index: int) -> WorkflowStep:
    if isinstance(d, str):
        d = json.loads(d)
    return WorkflowStep(
        task=d["task"],
        agent_hint=d.get("agent_hint"),
        verify=d.get("verify"),
        intent=d.get("intent", "execute"),
        id=d.get("id") or f"s{index}",
        branches=[
            Branch(condition=b["condition"], to=b["to"])
            for b in d.get("branches") or []
        ],
        default_next=d.get("default_next"),
        on_failure=d.get("on_failure", "fail"),
    )


def _step_result_to_dict(r: StepResult) -> dict:
    data = {
        "step_index": r.step_index,
        "task": r.task,
        "output": r.output,
        "success": r.success,
        "error": r.error,
        "duration_ms": r.duration_ms,
        "step_id": r.step_id,
        "branch_taken": r.branch_taken,
    }
    if r.attempt_count != 1:
        data["attempt_count"] = r.attempt_count
    if r.no_results:
        data["no_results"] = True
    return data


def _step_result_from_dict(d: dict | str) -> StepResult:
    if isinstance(d, str):
        d = json.loads(d)
    return StepResult(
        step_index=d["step_index"],
        task=d["task"],
        output=d.get("output", ""),
        success=d["success"],
        error=d.get("error"),
        duration_ms=d.get("duration_ms", 0),
        step_id=d.get("step_id", ""),
        branch_taken=d.get("branch_taken"),
        attempt_count=d.get("attempt_count", 1),
        no_results=d.get("no_results", False),
    )


def _row_to_execution(row) -> WorkflowExecution:
    return WorkflowExecution(
        id=row["id"],
        workflow_id=row["workflow_id"],
        status=row["status"],
        step_results=[
            _step_result_from_dict(d) for d in _coerce_jsonb_list(row["step_results"])
        ],
        steps_snapshot=[
            _step_from_dict(s, i)
            for i, s in enumerate(_coerce_jsonb_list(row.get("steps_snapshot")))
        ],
        error=row["error"],
        summary=row["summary"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        created_at=row["created_at"],
    )


def _row_to_revision(row) -> WorkflowRevision:
    return WorkflowRevision(
        id=row["id"],
        workflow_id=row["workflow_id"],
        revision_number=row["revision_number"],
        change_type=row["change_type"],
        steps_before=[
            _step_from_dict(s, i)
            for i, s in enumerate(_coerce_jsonb_list(row["steps_before"]))
        ],
        steps_after=[
            _step_from_dict(s, i)
            for i, s in enumerate(_coerce_jsonb_list(row["steps_after"]))
        ],
        summary=row["summary"],
        actor=ActorContext(
            source=ActorSource(row["actor_source"]),
            session_id=row["actor_session_id"],
            user_message_id=(
                str(row["actor_user_message_id"])
                if row["actor_user_message_id"]
                else None
            ),
        ),
        created_at=row["created_at"],
    )


def _row_to_workflow(row) -> Workflow:
    return Workflow(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        steps=[
            _step_from_dict(s, i)
            for i, s in enumerate(_coerce_jsonb_list(row["steps"]))
        ],
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

    async def create(
        self, workflow: Workflow, actor: ActorContext | None = None
    ) -> UUID:
        actor = actor or ActorContext(source=ActorSource.SYSTEM)
        steps_after = [_step_to_dict(s) for s in workflow.steps]
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO workflows (name, description, steps, schedule, enabled, next_run_at)
                    VALUES ($1, $2, $3::jsonb, $4, $5, $6)
                    RETURNING id
                    """,
                    workflow.name,
                    workflow.description,
                    steps_after,
                    workflow.schedule,
                    workflow.enabled,
                    workflow.next_run_at,
                )
                workflow_id = row["id"]
                summary = build_change_summary([], workflow.steps, "created")
                await conn.execute(
                    """
                    INSERT INTO workflow_revisions (
                        workflow_id, revision_number, change_type, steps_before,
                        steps_after, summary, actor_source, actor_session_id,
                        actor_user_message_id
                    )
                    VALUES ($1, 1, 'created', '[]'::jsonb, $2::jsonb, $3, $4, $5, $6::uuid)
                    """,
                    workflow_id,
                    steps_after,
                    summary,
                    actor.source.value,
                    actor.session_id,
                    actor.user_message_id,
                )
            log.info("workflow_created", name=workflow.name, id=str(workflow_id))
            return workflow_id

    async def get(self, workflow_id: UUID) -> Workflow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM workflows WHERE id = $1", workflow_id
            )
        return _row_to_workflow(row) if row else None

    async def get_by_name(self, name: str) -> Workflow | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM workflows WHERE name = $1", name)
        return _row_to_workflow(row) if row else None

    async def list_all(self) -> list[Workflow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM workflows ORDER BY created_at DESC")
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
                enabled,
                workflow_id,
            )

    async def update_schedule(
        self,
        workflow_id: UUID,
        schedule: str | None,
        next_run_at: datetime | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflows
                SET schedule = $1, next_run_at = $2, updated_at = NOW()
                WHERE id = $3
                """,
                schedule,
                next_run_at,
                workflow_id,
            )
        log.info("workflow_schedule_updated", id=str(workflow_id), schedule=schedule)

    async def update_steps(
        self,
        workflow_id: UUID,
        steps: list[WorkflowStep],
        actor: ActorContext | None = None,
    ) -> None:
        validate_workflow_steps(steps)
        actor = actor or ActorContext(source=ActorSource.SYSTEM)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT steps FROM workflows WHERE id = $1", workflow_id
                )
                if row is None:
                    raise WorkflowPlanError(f"Workflow {workflow_id} not found")
                current_steps = [
                    _step_from_dict(s, i)
                    for i, s in enumerate(_coerce_jsonb_list(row["steps"]))
                ]
                steps_before = [_step_to_dict(s) for s in current_steps]
                steps_after = [_step_to_dict(s) for s in steps]
                await conn.execute(
                    """
                    UPDATE workflows
                    SET steps = $1::jsonb, updated_at = NOW()
                    WHERE id = $2
                    """,
                    steps_after,
                    workflow_id,
                )
                if steps_after != steps_before:
                    rev_row = await conn.fetchrow(
                        """
                        SELECT COALESCE(MAX(revision_number), 0) + 1 AS next
                        FROM workflow_revisions WHERE workflow_id = $1
                        """,
                        workflow_id,
                    )
                    revision_number = rev_row["next"]
                    summary = build_change_summary(current_steps, steps, "edited")
                    await conn.execute(
                        """
                        INSERT INTO workflow_revisions (
                            workflow_id, revision_number, change_type, steps_before,
                            steps_after, summary, actor_source, actor_session_id,
                            actor_user_message_id
                        )
                        VALUES ($1, $2, 'edited', $3::jsonb, $4::jsonb, $5, $6, $7, $8::uuid)
                        """,
                        workflow_id,
                        revision_number,
                        steps_before,
                        steps_after,
                        summary,
                        actor.source.value,
                        actor.session_id,
                        actor.user_message_id,
                    )
        log.info("workflow_steps_updated", id=str(workflow_id), steps=len(steps))

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
                last_run_at,
                next_run_at,
                workflow_id,
            )

    async def start_execution(self, workflow_id: UUID | None) -> UUID:
        async with self._pool.acquire() as conn:
            snapshot: list[dict] = []
            if workflow_id is not None:
                wf_row = await conn.fetchrow(
                    "SELECT steps FROM workflows WHERE id = $1", workflow_id
                )
                if wf_row is not None:
                    snapshot = [
                        _step_to_dict(_step_from_dict(s, i))
                        for i, s in enumerate(_coerce_jsonb_list(wf_row["steps"]))
                    ]
            row = await conn.fetchrow(
                """
                INSERT INTO workflow_executions (workflow_id, status, started_at, steps_snapshot)
                VALUES ($1, 'running', NOW(), $2::jsonb)
                RETURNING id
                """,
                workflow_id,
                snapshot,
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
                [_step_result_to_dict(result)],
                execution_id,
            )

    async def finish_execution(
        self,
        execution_id: UUID,
        status: str,
        error: str | None = None,
        summary: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE workflow_executions
                SET status = $1, error = $2, summary = $3, completed_at = NOW()
                WHERE id = $4
                """,
                status,
                error,
                summary,
                execution_id,
            )

    async def list_executions(
        self, workflow_id: UUID, limit: int = 20
    ) -> list[WorkflowExecution]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_executions
                WHERE workflow_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                workflow_id,
                limit,
            )
        return [_row_to_execution(r) for r in rows]

    async def get_execution(
        self, workflow_id: UUID, execution_id: UUID
    ) -> WorkflowExecution | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM workflow_executions
                WHERE workflow_id = $1 AND id = $2
                """,
                workflow_id,
                execution_id,
            )
        if row is None:
            return None
        return _row_to_execution(row)

    async def list_revisions(
        self, workflow_id: UUID, limit: int = 20, offset: int = 0
    ) -> list[WorkflowRevision]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM workflow_revisions
                WHERE workflow_id = $1
                ORDER BY revision_number DESC
                LIMIT $2 OFFSET $3
                """,
                workflow_id,
                limit,
                offset,
            )
        return [_row_to_revision(r) for r in rows]

    async def recover_stale(self, timeout_minutes: int) -> int:
        """Mark running executions older than timeout_minutes as failed. Returns count recovered."""
        async with self._pool.acquire() as conn:
            tag = await conn.execute(
                """
                UPDATE workflow_executions
                SET status = 'failed',
                    error = 'Execution interrupted (process restarted mid-run)',
                    completed_at = NOW()
                WHERE status = 'running'
                  AND started_at < NOW() - ($1 * INTERVAL '1 minute')
                """,
                timeout_minutes,
            )
        parts = tag.split() if isinstance(tag, str) else []
        count = int(parts[-1]) if parts else 0
        if count:
            log.info(
                "stale_workflow_executions_recovered",
                count=count,
                timeout_minutes=timeout_minutes,
            )
        return count
