from __future__ import annotations

import time
from typing import Any

from ze_logging import get_logger
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

    async def run(self) -> None:
        run_id = await self._dream_store.create_run()
        sleep_stats: dict = {}
        error: str | None = None

        try:
            sleep_stats = await self._sleep_pass.run(run_id)
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
