"""Morning Integration: support validation, auto-promote, forgetting, rollback, confidence decay."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from ze_logging import get_logger
from ze_memory.dream.types import ArtifactStatus, ArtifactType

log = get_logger(__name__)

_DEFAULT_MIN_SUPPORT = 3
_DEFAULT_MIN_DISTINCT_SESSIONS = 2
_DEFAULT_MIN_TEMPORAL_SPREAD_DAYS = 7
_DEFAULT_MAX_USER_ASSERTED = 1
_DEFAULT_SYNTHETIC_FACT_VALID_DAYS = 90
_DEFAULT_DECAY_RATE = 0.1


class DreamPromoter:
    def __init__(
        self,
        pool: Any,
        dream_store: Any,
        embedder: Any | None = None,
        settings: Any = None,
    ) -> None:
        self._pool = pool
        self._dream_store = dream_store
        self._embedder = embedder
        self._settings = settings

    async def run_morning_integration(self, run_id: UUID) -> dict:
        start = time.monotonic()
        cfg = self._config()

        min_support = int(cfg.get("auto_promote_min_support", _DEFAULT_MIN_SUPPORT))
        min_sessions = int(cfg.get("auto_promote_min_distinct_sessions", _DEFAULT_MIN_DISTINCT_SESSIONS))
        min_spread = int(cfg.get("auto_promote_min_temporal_spread_days", _DEFAULT_MIN_TEMPORAL_SPREAD_DAYS))
        max_user_asserted = int(cfg.get("auto_promote_max_user_asserted", _DEFAULT_MAX_USER_ASSERTED))
        valid_days = int(cfg.get("synthetic_fact_valid_days", _DEFAULT_SYNTHETIC_FACT_VALID_DAYS))
        decay_rate = float(cfg.get("decay_rate", _DEFAULT_DECAY_RATE))

        pending_artifacts = await self._dream_store.get_pending_artifacts_for_run(run_id)

        promoted = 0
        needs_review = 0
        rejected = 0

        for row in pending_artifacts:
            artifact_id = row["id"]
            artifact_type = row["artifact_type"]

            # Already rejected by scoring pipeline
            if row["status"] == ArtifactStatus.REJECTED.value:
                rejected += 1
                continue

            # hindsight_fact always goes to needs_review
            if artifact_type == ArtifactType.HINDSIGHT_FACT.value:
                await self._dream_store.update_artifact_status(artifact_id, ArtifactStatus.NEEDS_REVIEW.value)
                needs_review += 1
                continue

            # Support validation
            passes_support = (
                row.get("support_count", 0) >= min_support
                and row.get("distinct_session_count", 0) >= min_sessions
                and row.get("temporal_spread_days", 0) >= min_spread
                and row.get("user_asserted_source_count", 0) <= max_user_asserted
            )

            # Critic must have passed (both a and b PASS)
            critic_passed = (
                row.get("critic_a_verdict") == "PASS"
                and row.get("critic_b_verdict") == "PASS"
            )

            if not critic_passed:
                await self._dream_store.update_artifact_status(artifact_id, ArtifactStatus.REJECTED.value)
                await self._decay_source_episodes(row.get("source_episode_ids") or [], decay_rate)
                rejected += 1
                continue

            if passes_support:
                await self._promote(row, run_id, valid_days)
                promoted += 1
            else:
                await self._dream_store.update_artifact_status(artifact_id, ArtifactStatus.NEEDS_REVIEW.value)
                needs_review += 1

        # Synthetic fact confidence decay + hard expiry at valid_until
        await self._run_confidence_decay()
        await self._expire_stale_synthetic_facts()

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info(
            "morning_integration_complete",
            promoted=promoted,
            needs_review=needs_review,
            rejected=rejected,
            duration_ms=duration_ms,
        )
        return {
            "promoted": promoted,
            "needs_review": needs_review,
            "rejected": rejected,
            "duration_ms": duration_ms,
        }

    async def _promote(self, row: dict, run_id: UUID, valid_days: int) -> None:
        artifact_id = row["id"]
        artifact_type = row["artifact_type"]
        content = row.get("user_revised_content") or row["content"]
        valid_until = datetime.now(tz=timezone.utc) + timedelta(days=valid_days)

        if artifact_type == ArtifactType.SYNTHESIZED_INSIGHT.value:
            fact_id = await self._insert_fact(
                content=content,
                run_id=run_id,
                source_fact_ids=row.get("source_fact_ids") or [],
                valid_until=valid_until,
            )
            await self._dream_store.mark_artifact_promoted(
                artifact_id,
                promoted_to="memory_facts",
                promoted_id=fact_id,
            )

        elif artifact_type in (
            ArtifactType.SYNTHESIZED_PROCEDURE.value,
            ArtifactType.PLAN_STRESS_TEST.value,
        ):
            proc_id = await self._insert_procedure(content=content, run_id=run_id)
            await self._dream_store.mark_artifact_promoted(
                artifact_id,
                promoted_to="memory_procedures",
                promoted_id=proc_id,
            )
        else:
            # Unknown type — mark promoted without a target record
            await self._dream_store.mark_artifact_promoted(artifact_id)

    async def _insert_fact(
        self,
        content: str,
        run_id: UUID,
        source_fact_ids: list[Any],
        valid_until: datetime,
    ) -> UUID:
        embedding = None
        if self._embedder is not None:
            try:
                embedding = list(self._embedder.encode(content))
            except Exception:
                pass

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_facts (
                    predicate, value, embedding, confidence, reviewed,
                    provenance, valid_until, dream_run_id, derived_from,
                    corroborated, creation_method, agent
                ) VALUES (
                    'synthesized_insight', $1, $2::vector, 0.7, false,
                    'synthesized', $3, $4, $5,
                    false, 'synthesized', 'dream'
                )
                RETURNING id
                """,
                content,
                embedding,
                valid_until,
                run_id,
                [str(fid) for fid in source_fact_ids],
            )
        return row["id"]

    async def _insert_procedure(self, content: str, run_id: UUID) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_procedures (
                    name, trigger, steps, creation_method, dream_run_id
                ) VALUES (
                    $1, '', ARRAY[$1], 'synthesized', $2
                )
                RETURNING id
                """,
                content[:200],
                run_id,
            )
        return row["id"]

    async def apply_user_decision(
        self,
        artifact_id: UUID,
        decision: str,
        revised_content: str | None = None,
        valid_days: int = _DEFAULT_SYNTHETIC_FACT_VALID_DAYS,
    ) -> None:
        """Apply user approve / reject / revise decision from the REST API."""
        row = await self._dream_store.get_artifact_row(artifact_id)
        if row is None:
            return

        if decision == "reject":
            await self._dream_store.update_artifact_status(
                artifact_id, ArtifactStatus.REJECTED.value
            )
            await self._dream_store.mark_artifact_reviewed(artifact_id)
            await self._decay_source_episodes(row.get("source_episode_ids") or [])
            return

        if decision == "revise" and revised_content:
            await self._dream_store.set_revised_content(artifact_id, revised_content)
            row = dict(row)
            row["user_revised_content"] = revised_content
            row["status"] = ArtifactStatus.REVISED.value

        # approve or revise → promote
        async with self._pool.acquire() as conn:
            run_row = await conn.fetchrow(
                "SELECT id FROM memory_dream_runs WHERE id = $1", row["run_id"]
            )
        run_id = run_row["id"] if run_row else row["run_id"]

        await self._promote(row, run_id, valid_days)
        await self._dream_store.mark_artifact_reviewed(artifact_id)

    async def rollback_run(self, run_id: UUID) -> dict:
        """Bulk-mark all promoted artifacts from a run as rolled back and contradict promoted facts."""
        async with self._pool.acquire() as conn:
            # Get all promoted artifacts for this run
            rows = await conn.fetch(
                """
                SELECT id, promoted_to, promoted_id
                FROM memory_dream_artifacts
                WHERE run_id = $1 AND status = $2
                """,
                run_id,
                ArtifactStatus.PROMOTED.value,
            )

            rolled_back = 0
            for row in rows:
                await conn.execute(
                    "UPDATE memory_dream_artifacts SET status = $2 WHERE id = $1",
                    row["id"],
                    ArtifactStatus.ROLLED_BACK.value,
                )
                if row["promoted_to"] == "memory_facts" and row["promoted_id"]:
                    await conn.execute(
                        "UPDATE memory_facts SET contradicted = true WHERE id = $1",
                        row["promoted_id"],
                    )
                    # Flag derived_from chains for re-evaluation
                    await conn.execute(
                        """
                        UPDATE memory_facts SET reviewed = false
                        WHERE $1::uuid = ANY(derived_from)
                        """,
                        row["promoted_id"],
                    )
                rolled_back += 1

            # Clear contaminated session summaries
            resummary = await conn.fetchval(
                """
                UPDATE memory_session_summaries SET
                    needs_resummary = true
                WHERE dream_artifact_ids && (
                    SELECT array_agg(id) FROM memory_dream_artifacts WHERE run_id = $1
                )
                RETURNING count(*)
                """,
                run_id,
            ) or 0

        log.info("dream_rollback_complete", run_id=str(run_id), rolled_back=rolled_back)
        return {"rolled_back": rolled_back, "summaries_flagged": int(resummary)}

    async def _run_confidence_decay(self) -> None:
        """Decrement confidence on non-corroborated synthetic facts older than 30 days."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_facts SET
                    confidence = GREATEST(0.0, confidence - 0.03),
                    reviewed = CASE
                        WHEN GREATEST(0.0, confidence - 0.03) < 0.50 THEN false
                        ELSE reviewed
                    END,
                    contradicted = CASE
                        WHEN GREATEST(0.0, confidence - 0.03) < 0.25 THEN true
                        ELSE contradicted
                    END
                WHERE provenance = 'synthesized'
                  AND corroborated = false
                  AND created_at < now() - interval '30 days'
                  AND contradicted = false
                """
            )

    async def _expire_stale_synthetic_facts(self) -> None:
        """Contradict synthesized facts that have passed their valid_until deadline."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE memory_facts SET
                    contradicted = true,
                    reviewed = false
                WHERE provenance = 'synthesized'
                  AND corroborated = false
                  AND contradicted = false
                  AND valid_until IS NOT NULL
                  AND valid_until < now()
                """
            )
        expired = int(result.split()[-1]) if result else 0
        if expired:
            log.info("synthetic_facts_expired", count=expired)

    async def _decay_source_episodes(self, episode_ids: list[Any], rate: float = _DEFAULT_DECAY_RATE) -> None:
        if not episode_ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_episode_metadata SET
                    retrieval_weight = GREATEST(0.0, retrieval_weight - $2),
                    updated_at = now()
                WHERE episode_id = ANY($1::uuid[])
                """,
                list(episode_ids),
                rate,
            )

    def _config(self) -> dict:
        if self._settings is None:
            return {}
        if isinstance(self._settings, dict):
            return self._settings.get("dream", {})
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("dream", {})
        return {}
