from __future__ import annotations

import asyncio
from typing import Any

from ze_logging import get_logger
from ze_memory.defaults import DREAM_JOB_TIMEOUT_SECONDS
from ze_memory.dream.dream_pass import DreamPass
from ze_memory.dream.journal import DreamJournal
from ze_memory.dream.promoter import DreamPromoter
from ze_memory.dream.sleep_pass import SleepPass
from ze_memory.retrieval_cache import expire_retrieval_cache
from ze_proactive.job import proactive_job

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
        client: Any | None = None,
        nli_client: Any | None = None,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._dream_store = dream_store
        self._client = client
        self._settings = settings
        self._sleep_pass = SleepPass(
            pool=pool,
            embedder=embedder,
            consolidator=consolidator,
            dream_store=dream_store,
            settings=settings,
        )
        self._dream_pass = DreamPass(
            pool=pool,
            dream_store=dream_store,
            client=client,
            embedder=embedder,
            nli_client=nli_client,
            settings=settings,
        ) if client is not None else None
        self._promoter = DreamPromoter(
            pool=pool,
            dream_store=dream_store,
            embedder=embedder,
            settings=settings,
        )
        self._journal = DreamJournal(client=client, dream_store=dream_store) if client is not None else None

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
        cfg = self._dream_config()
        timeout = int(cfg.get("job_timeout_seconds", DREAM_JOB_TIMEOUT_SECONDS))
        synthesis_model = cfg.get("synthesis_model", "anthropic/claude-haiku-4-5")

        sleep_stats: dict = {}
        dream_stats: dict = {}
        integration_stats: dict = {}
        error: str | None = None

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

        if error is None and self._dream_pass is not None:
            try:
                dream_stats = await asyncio.wait_for(
                    self._dream_pass.run(run_id),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                error = f"dream pass timed out after {timeout}s"
                log.error("dream_dream_pass_timeout", run_id=str(run_id))
            except Exception as exc:
                error = str(exc)
                log.error("dream_dream_pass_failed", run_id=str(run_id), error=error)

        if error is None:
            try:
                integration_stats = await asyncio.wait_for(
                    self._promoter.run_morning_integration(run_id),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                error = f"morning integration timed out after {timeout}s"
                log.error("dream_integration_timeout", run_id=str(run_id))
            except Exception as exc:
                error = str(exc)
                log.error("dream_integration_failed", run_id=str(run_id), error=error)

        episodes_scored = sleep_stats.get("episodes_scored", 0)
        episodes_replayed = sleep_stats.get("episodes_replayed", 0)
        artifacts_generated = dream_stats.get("artifacts_scored", 0)
        artifacts_promoted = integration_stats.get("promoted", 0)
        artifacts_rejected = integration_stats.get("rejected", 0)
        artifacts_pending = integration_stats.get("needs_review", 0)

        await self._dream_store.finish_run(
            run_id,
            episodes_scored=episodes_scored,
            episodes_replayed=episodes_replayed,
            artifacts_generated=artifacts_generated,
            artifacts_promoted=artifacts_promoted,
            artifacts_rejected=artifacts_rejected,
            artifacts_pending=artifacts_pending,
            sleep_pass_duration_ms=sleep_stats.get("duration_ms"),
            dream_pass_duration_ms=dream_stats.get("duration_ms"),
            integration_duration_ms=integration_stats.get("duration_ms"),
            error=error,
        )

        expired = await expire_retrieval_cache(self._pool)
        if expired:
            log.info("retrieval_cache_expired", rows_deleted=expired)

        if error is None and self._journal is not None:
            await self._journal.write_entry(
                run_id=run_id,
                episodes_processed=episodes_scored,
                insights_promoted=artifacts_promoted,
                procedures_extracted=dream_stats.get("policies", 0),
                plan_risks_surfaced=dream_stats.get("stress_tests", 0),
                pending_review=artifacts_pending,
                synthesis_model=synthesis_model,
            )

        log.info(
            "dream_job_complete",
            run_id=str(run_id),
            episodes_scored=episodes_scored,
            episodes_replayed=episodes_replayed,
            artifacts_generated=artifacts_generated,
            artifacts_promoted=artifacts_promoted,
            artifacts_rejected=artifacts_rejected,
            artifacts_pending=artifacts_pending,
        )
