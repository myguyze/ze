from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import UUID

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from ze_core.logging import get_logger
from ze_personal.workflow.store import WorkflowStore
from ze_personal.workflow.types import Workflow

log = get_logger(__name__)

WorkflowExecutor = Callable[[Workflow, UUID], Awaitable[None]]
WorkflowFailureHandler = Callable[[Workflow, Exception], Awaitable[None]]


class WorkflowScheduler:
    def __init__(
        self,
        workflow_store: WorkflowStore,
        executor: WorkflowExecutor,
        enabled: bool = True,
        on_failure: WorkflowFailureHandler | None = None,
    ) -> None:
        self._store = workflow_store
        self._executor = executor
        self._enabled = enabled
        self._on_failure = on_failure
        self._scheduler = AsyncIOScheduler()

    async def start(self) -> None:
        if not self._enabled:
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

        execution_id = await self._store.start_execution(workflow_id)
        log.info("workflow_execution_start", workflow=workflow.name, execution_id=str(execution_id))

        try:
            await self._executor(workflow, execution_id)
        except Exception as exc:
            log.exception("workflow_execution_error", workflow=workflow.name, error=str(exc))
            await self._store.finish_execution(execution_id, "failed", error=str(exc))
            if self._on_failure:
                await self._on_failure(workflow, exc)
            return

        now = datetime.now(tz=timezone.utc)
        trigger = CronTrigger.from_crontab(workflow.schedule) if workflow.schedule else None
        next_run = trigger.get_next_fire_time(None, now) if trigger else None
        await self._store.update_run_timestamps(workflow_id, now, next_run)
        log.info("workflow_execution_done", workflow=workflow.name, execution_id=str(execution_id))
