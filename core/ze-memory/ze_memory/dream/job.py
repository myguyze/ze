from __future__ import annotations

import asyncio
import time
from typing import Any

from ze_logging import get_logger
from ze_memory.defaults import DREAM_JOB_TIMEOUT_SECONDS
from ze_proactive.job import proactive_job
from ze_memory.dream.sleep_pass import SleepPass

log = get_logger(__name__)


@proactive_job
class DreamJob:
    job_id = "dream_memory"

    def __init__(
        self,
        pool: Any,
        embedder: Any,
        consolidator: Any,
        dream_store: Any,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._dream_store = dream_store
        self._settings = settings
        self._sleep_pass = SleepPass(
            pool=pool,
            embedder=embedder,
            consolidator=consolidator,
            dream_store=dream_store,
            settings=settings,
        )

    def _dream_config(self) -> dict:
        if self._settings is None:
            return {}
        dream = getattr(self._settings, "dream_config", None)
        if isinstance(dream, dict):
            return dream
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("dream", {})
        return {}

    async def run(self) -> None:
        run_id = await self._dream_store.create_run()
        sleep_stats: dict = {}
        error: str | None = None
        cfg = self._dream_config()
        timeout = int(cfg.get("job_timeout_seconds", DREAM_JOB_TIMEOUT_SECONDS))

        try:
            sleep_stats = await asyncio.wait_for(
                self._sleep_pass.run(run_id),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            error = f"sleep pass timed out after {timeout}s"
            log.error("dream_sleep_pass_timeout", run_id=str(run_id), timeout_seconds=timeout)
        except Exception as exc:
            error = str(exc)
            log.error("dream_sleep_pass_failed", run_id=str(run_id), error=error)

        episodes_scored = sleep_stats.get("episodes_scored", 0)
        episodes_replayed = sleep_stats.get("episodes_replayed", 0)
        schema_candidates = sleep_stats.get("schema_candidates", 0)
        policy_candidates = sleep_stats.get("policy_candidates", 0)
        artifacts_generated = schema_candidates + policy_candidates

        await self._dream_store.finish_run(
            run_id,
            episodes_scored=episodes_scored,
            episodes_replayed=episodes_replayed,
            artifacts_generated=artifacts_generated,
            sleep_pass_duration_ms=sleep_stats.get("duration_ms"),
            error=error,
        )

        if error is None:
            summary = (
                f"Ze processed {episodes_scored} episodes overnight. "
                f"{episodes_replayed} selected for replay. "
                f"{schema_candidates} schema candidates and "
                f"{policy_candidates} policy candidates queued for Phase 78b synthesis."
            )
            await self._dream_store.write_journal_entry(
                run_id=run_id,
                summary=summary,
                episodes_processed=episodes_scored,
            )

        log.info(
            "dream_job_complete",
            run_id=str(run_id),
            episodes_scored=episodes_scored,
            episodes_replayed=episodes_replayed,
            artifacts_generated=artifacts_generated,
        )
