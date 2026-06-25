from __future__ import annotations

import os
from typing import Any

from ze_logging import get_logger
from ze_memory.defaults import SESSION_SUMMARY_CHECK_INTERVAL_MINUTES
from ze_memory.session_summary import SessionSummariser
from ze_proactive.scheduler import ProactiveScheduler

log = get_logger(__name__)


def dream_enabled(settings: Any) -> bool:
    cfg = getattr(settings, "config", None) or {}
    return bool(cfg.get("dream", {}).get("enabled", False))


def register_dream_jobs(
    scheduler: ProactiveScheduler,
    settings: Any,
    dream_job: Any,
) -> None:
    if not dream_enabled(settings):
        return
    cfg = (getattr(settings, "config", None) or {}).get("dream", {})
    cron = cfg.get("cron", "0 3 * * *")
    scheduler.add_cron_job(fn=dream_job.run, cron=cron, job_id=dream_job.job_id)
    log.info("dream_job_scheduled", cron=cron)


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
