from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from ze.logging import get_logger
from ze.settings import Settings
from ze.telemetry.context import set_flow_context
from ze.workflow.store import WorkflowStore
from ze.workflow.types import Workflow

log = get_logger(__name__)


class WorkflowScheduler:
    def __init__(
        self,
        workflow_store: WorkflowStore,
        workflow_graph,
        graph_config: dict,
        settings: Settings,
        pool: asyncpg.Pool | None = None,
        notifier=None,  # ProactiveNotifier | None — avoids circular import
    ) -> None:
        self._store = workflow_store
        self._graph = workflow_graph
        self._graph_config = graph_config
        self._settings = settings
        self._pool = pool
        self._notifier = notifier
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        if not self._settings.scheduler_enabled:
            log.info("workflow_scheduler_disabled")
            return

        workflows = await self._store.list_enabled_scheduled()
        for wf in workflows:
            self._add_job(wf)

        self._scheduler.start()
        log.info("workflow_scheduler_started", jobs=len(workflows))

    async def stop(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            log.info("workflow_scheduler_stopped")

    async def add_workflow(self, workflow: Workflow) -> None:
        if not workflow.schedule or not workflow.enabled:
            return
        self._add_job(workflow)
        log.info("workflow_scheduled", name=workflow.name, schedule=workflow.schedule)

    async def remove_workflow(self, workflow_id: UUID) -> None:
        job_id = str(workflow_id)
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            log.info("workflow_unscheduled", id=job_id)

    async def trigger_now(self, workflow_id: UUID) -> None:
        await self._run_workflow(workflow_id)

    def schedule_job(self, fn, cron: str, job_id: str) -> None:
        self._scheduler.add_job(
            fn,
            trigger=CronTrigger.from_crontab(cron),
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def schedule_at(self, fn, dt: datetime, job_id: str, args: tuple = ()) -> None:
        self._scheduler.add_job(
            fn,
            trigger=DateTrigger(run_date=dt),
            id=job_id,
            args=list(args),
            replace_existing=True,
            max_instances=1,
        )

    def remove_job_if_exists(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    # ── Private ───────────────────────────────────────────────────────────────

    def _add_job(self, workflow: Workflow) -> None:
        self._scheduler.add_job(
            self._run_workflow,
            trigger=CronTrigger.from_crontab(workflow.schedule),
            id=str(workflow.id),
            args=[workflow.id],
            replace_existing=True,
        )

    async def _run_workflow(self, workflow_id: UUID) -> None:
        workflow = await self._store.get(workflow_id)
        if workflow is None or not workflow.enabled:
            return

        set_flow_context("workflow_execution", session_id=f"workflow:{workflow_id}")
        execution_id = await self._store.start_execution(workflow_id)
        log.info("workflow_execution_start", workflow=workflow.name, execution_id=str(execution_id))

        initial_state = {
            "prompt": f"[workflow] {workflow.name}",
            "session_id": f"workflow:{workflow_id}",
            "session_overrides": {},
            "envelope": None,
            "memory_context": None,
            "agent_context": None,
            "gate_decision": None,
            "agent_result": None,
            "subtask_results": [],
            "pending_confirmation": False,
            "messages": [],
            "last_active_at": None,
            "workflow_id": workflow_id,
            "workflow_execution_id": execution_id,
            "workflow_steps": workflow.steps,
            "current_step_index": 0,
            "workflow_step_results": [],
            "final_response": None,
            "error": None,
        }

        run_config = {
            **self._graph_config,
            "configurable": {
                **self._graph_config.get("configurable", {}),
                "thread_id": str(execution_id),
                "workflow_store": self._store,
            },
        }

        try:
            await self._graph.ainvoke(initial_state, run_config)
        except Exception as exc:
            log.exception("workflow_execution_error", workflow=workflow.name, error=str(exc))
            await self._store.finish_execution(execution_id, "failed", error=str(exc))
            if self._notifier:
                await self._push_failure_alert(workflow, exc)
            return

        now = datetime.now(tz=timezone.utc)
        trigger = CronTrigger.from_crontab(workflow.schedule) if workflow.schedule else None
        next_run = trigger.get_next_fire_time(None, now) if trigger else None
        await self._store.update_run_timestamps(workflow_id, now, next_run)

        log.info("workflow_execution_done", workflow=workflow.name, execution_id=str(execution_id))

    async def _push_failure_alert(self, workflow: Workflow, exc: Exception) -> None:
        alerts_cfg = self._settings.proactive_config.get("alerts", {})
        if not alerts_cfg.get("workflow_failure_enabled", True):
            return

        cooldown = int(alerts_cfg.get("workflow_failure_cooldown_hours", 1))
        event_type = f"workflow_failure:{workflow.id}"

        if self._pool is not None:
            async with self._pool.acquire() as conn:
                existing = await conn.fetchrow(
                    "SELECT 1 FROM push_log WHERE event_type = $1 "
                    "AND sent_at > NOW() - ($2 * INTERVAL '1 hour')",
                    event_type, cooldown,
                )
            if existing:
                log.info("failure_alert_suppressed_cooldown", workflow=workflow.name)
                return

        await self._notifier.push(
            f"⚠️ Workflow failed: *{workflow.name}*\n`{str(exc)[:200]}`"
        )

        if self._pool is not None:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO push_log (event_type, payload) VALUES ($1, $2)",
                    event_type, workflow.name,
                )
        log.info("failure_alert_sent", workflow=workflow.name)
