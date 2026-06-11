from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable

from ze_core.logging import get_logger

if TYPE_CHECKING:
    from ze_core.proactive.job import ProactiveJob

log = get_logger(__name__)


class ProactiveScheduler:
    """Thin wrapper around APScheduler's AsyncIOScheduler.

    Manages cron-based proactive jobs (briefings, insights, sweeps).
    Jobs are registered before start() is called. The scheduler is
    in-process only — jobs do not persist across restarts, but they
    are re-registered from config on each startup.

    Requires APScheduler >= 3.x:
        pip install apscheduler
    """

    def __init__(self) -> None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        self._scheduler = AsyncIOScheduler()
        self._started = False

    def register(self, job: "ProactiveJob", cron: str) -> None:
        """Register a ProactiveJob instance on a cron schedule."""
        self.add_cron_job(fn=job.run, cron=cron, job_id=job.job_id)

    def add_cron_job(
        self,
        fn: Callable[[], Awaitable[None]],
        cron: str,
        job_id: str,
    ) -> None:
        """Register a cron job. Safe to call before or after start()."""
        from apscheduler.triggers.cron import CronTrigger
        self._scheduler.add_job(
            fn,
            trigger=CronTrigger.from_crontab(cron),
            id=job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        log.info("proactive_job_registered", job_id=job_id, cron=cron)

    def remove_job(self, job_id: str) -> None:
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)
            log.info("proactive_job_removed", job_id=job_id)

    async def start(self) -> None:
        if self._started:
            return
        self._scheduler.start()
        self._started = True
        log.info("proactive_scheduler_started", jobs=len(self._scheduler.get_jobs()))

    async def stop(self) -> None:
        if self._started and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            self._started = False
            log.info("proactive_scheduler_stopped")

    async def trigger_now(self, fn: Callable[[], Awaitable[None]]) -> None:
        """Run a job function immediately, outside the scheduler."""
        asyncio.create_task(fn())
