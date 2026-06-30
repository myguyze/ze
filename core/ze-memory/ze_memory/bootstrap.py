from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from ze_logging import get_logger
from ze_memory.defaults import SESSION_SUMMARY_CHECK_INTERVAL_MINUTES
from ze_memory.session_summary import SessionSummariser
from ze_proactive.scheduler import ProactiveScheduler

log = get_logger(__name__)

_DEFAULT_INACTIVITY_THRESHOLD_HOURS = 6
_DEFAULT_INACTIVITY_CHECK_INTERVAL_MINUTES = 30


def dream_enabled(settings: Any) -> bool:
    cfg = getattr(settings, "config", None) or {}
    return bool(cfg.get("dream", {}).get("enabled", False))


class DreamInactivityWatcher:
    """Fires the dream job when the user has been idle for N hours and no run completed today."""

    def __init__(self, pool: Any, dream_job: Any, settings: Any) -> None:
        self._pool = pool
        self._dream_job = dream_job
        self._settings = settings
        self._running = False

    def _cfg(self) -> dict:
        cfg = getattr(self._settings, "config", None) or {}
        return cfg.get("dream", {})

    async def check(self) -> None:
        if self._running:
            return
        cfg = self._cfg()
        threshold_hours = int(cfg.get("inactivity_threshold_hours", _DEFAULT_INACTIVITY_THRESHOLD_HOURS))

        async with self._pool.acquire() as conn:
            session_row = await conn.fetchrow(
                "SELECT MAX(last_active_at) AS last_active FROM sessions"
            )
            run_row = await conn.fetchrow(
                """
                SELECT finished_at FROM memory_dream_runs
                WHERE finished_at IS NOT NULL AND error IS NULL
                ORDER BY finished_at DESC LIMIT 1
                """
            )

        last_active: datetime | None = session_row["last_active"] if session_row else None
        last_run: datetime | None = run_row["finished_at"] if run_row else None

        if last_active is None:
            return

        now = datetime.now(tz=timezone.utc)
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)

        idle_hours = (now - last_active).total_seconds() / 3600
        if idle_hours < threshold_hours:
            return

        # Don't fire if a successful run already completed since the last active session
        if last_run is not None:
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
            if last_run > last_active:
                return

        log.info(
            "dream_inactivity_trigger",
            idle_hours=round(idle_hours, 1),
            threshold_hours=threshold_hours,
        )
        self._running = True
        try:
            await self._dream_job.run()
        finally:
            self._running = False


def register_dream_jobs(
    scheduler: ProactiveScheduler,
    settings: Any,
    dream_job: Any,
    pool: Any = None,
) -> None:
    if not dream_enabled(settings):
        return
    cfg = (getattr(settings, "config", None) or {}).get("dream", {})
    cron = cfg.get("cron", "0 3 * * *")
    scheduler.add_cron_job(fn=dream_job.run, cron=cron, job_id=dream_job.job_id)
    log.info("dream_job_scheduled", cron=cron)

    if pool is not None and cfg.get("inactivity_trigger_enabled", False):
        watcher = DreamInactivityWatcher(pool=pool, dream_job=dream_job, settings=settings)
        interval = int(cfg.get("inactivity_check_interval_minutes", _DEFAULT_INACTIVITY_CHECK_INTERVAL_MINUTES))
        scheduler.add_cron_job(
            fn=watcher.check,
            cron=f"*/{interval} * * * *",
            job_id="dream_inactivity_watcher",
        )
        log.info("dream_inactivity_watcher_scheduled", interval_minutes=interval)


def consolidation_enabled(settings: Any) -> bool:
    cfg = getattr(settings, "config", None) or {}
    mem = cfg.get("memory", {}).get("consolidation", {})
    if "enabled" in mem:
        return bool(mem["enabled"])
    return os.environ.get("CONSOLIDATION_ENABLED", "true").lower() != "false"


def _consolidation_config(settings: Any) -> dict:
    if hasattr(settings, "consolidation_config"):
        return settings.consolidation_config
    cfg = getattr(settings, "config", None) or {}
    return cfg.get("memory", {}).get("consolidation", {})


def register_memory_jobs(
    scheduler: ProactiveScheduler,
    settings: Any,
    shared: Any,
) -> None:
    if not consolidation_enabled(settings):
        return

    nightly_cron = _consolidation_config(settings).get("nightly_cron") or "0 2 * * *"
    scheduler.add_cron_job(
        fn=shared.memory_consolidator.run,
        cron=nightly_cron,
        job_id="memory_consolidation",
    )
    log.info("consolidation_scheduled", cron=nightly_cron)

    _ss_cfg = (getattr(settings, "config", {}) or {}).get("memory", {}).get("session_summary", {})
    _ss_interval = int(_ss_cfg.get("check_interval_minutes", SESSION_SUMMARY_CHECK_INTERVAL_MINUTES))
    _ss_enabled = _ss_cfg.get("enabled", True)
    if _ss_enabled:
        scheduler.add_cron_job(
            fn=shared.session_summariser.run,
            cron=f"*/{_ss_interval} * * * *",
            job_id=SessionSummariser.job_id,
        )
        log.info("session_summary_scheduled", interval_minutes=_ss_interval)
