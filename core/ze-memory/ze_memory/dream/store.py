from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from ze_logging import get_logger

log = get_logger(__name__)


class PostgresDreamStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def create_run(self) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO memory_dream_runs (started_at) VALUES (now()) RETURNING id",
            )
        return row["id"]

    async def finish_run(
        self,
        run_id: UUID,
        finished_at: datetime | None = None,
        *,
        episodes_scored: int = 0,
        episodes_replayed: int = 0,
        artifacts_generated: int = 0,
        artifacts_promoted: int = 0,
        artifacts_rejected: int = 0,
        artifacts_pending: int = 0,
        sleep_pass_duration_ms: int | None = None,
        dream_pass_duration_ms: int | None = None,
        integration_duration_ms: int | None = None,
        error: str | None = None,
    ) -> None:
        if finished_at is None:
            finished_at = datetime.now(tz=timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_dream_runs SET
                    finished_at             = $2,
                    episodes_scored         = $3,
                    episodes_replayed       = $4,
                    artifacts_generated     = $5,
                    artifacts_promoted      = $6,
                    artifacts_rejected      = $7,
                    artifacts_pending       = $8,
                    sleep_pass_duration_ms  = $9,
                    dream_pass_duration_ms  = $10,
                    integration_duration_ms = $11,
                    error                   = $12
                WHERE id = $1
                """,
                run_id,
                finished_at,
                episodes_scored,
                episodes_replayed,
                artifacts_generated,
                artifacts_promoted,
                artifacts_rejected,
                artifacts_pending,
                sleep_pass_duration_ms,
                dream_pass_duration_ms,
                integration_duration_ms,
                error,
            )

    async def save_artifact(
        self,
        run_id: UUID,
        artifact_type: str,
        content: str,
        source_episode_ids: list[UUID],
        source_fact_ids: list[UUID],
        support_count: int,
        distinct_session_count: int,
        temporal_spread_days: int,
        user_asserted_source_count: int,
    ) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_dream_artifacts (
                    run_id, artifact_type, content,
                    source_episode_ids, source_fact_ids,
                    support_count, distinct_session_count,
                    temporal_spread_days, user_asserted_source_count
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
                """,
                run_id,
                artifact_type,
                content,
                source_episode_ids,
                source_fact_ids,
                support_count,
                distinct_session_count,
                temporal_spread_days,
                user_asserted_source_count,
            )
        return row["id"]

    async def update_artifact_status(self, artifact_id: UUID, status: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_dream_artifacts SET status = $2 WHERE id = $1",
                artifact_id,
                status,
            )

    async def get_artifacts_by_status(self, status: str) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM memory_dream_artifacts WHERE status = $1 ORDER BY created_at DESC",
                status,
            )
        return [dict(r) for r in rows]

    async def write_journal_entry(
        self,
        run_id: UUID,
        summary: str,
        episodes_processed: int = 0,
        insights_promoted: int = 0,
        procedures_extracted: int = 0,
        plan_risks_surfaced: int = 0,
        pending_review: int = 0,
    ) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO memory_dream_journal (
                    run_id, summary, episodes_processed, insights_promoted,
                    procedures_extracted, plan_risks_surfaced, pending_review
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id
                """,
                run_id,
                summary,
                episodes_processed,
                insights_promoted,
                procedures_extracted,
                plan_risks_surfaced,
                pending_review,
            )
        return row["id"]

    async def get_latest_journal_entry(self) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM memory_dream_journal ORDER BY created_at DESC LIMIT 1"
            )
        return dict(row) if row else None

    async def list_journal_entries(self, limit: int = 10) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM memory_dream_journal ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [dict(r) for r in rows]

    async def get_artifact_row(self, artifact_id: UUID) -> dict | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM memory_dream_artifacts WHERE id = $1",
                artifact_id,
            )
        return dict(row) if row else None

    async def get_pending_artifacts_by_type(
        self, run_id: UUID, artifact_type: str
    ) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM memory_dream_artifacts
                WHERE run_id = $1 AND artifact_type = $2 AND status = 'pending'
                ORDER BY created_at
                """,
                run_id,
                artifact_type,
            )
        return [dict(r) for r in rows]

    async def get_pending_artifacts_for_run(self, run_id: UUID) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM memory_dream_artifacts
                WHERE run_id = $1 AND status IN ('pending', 'rejected')
                ORDER BY created_at
                """,
                run_id,
            )
        return [dict(r) for r in rows]

    async def get_needs_review_artifacts(self, limit: int = 50) -> list[dict]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM memory_dream_artifacts
                WHERE status = 'needs_review'
                ORDER BY created_at DESC
                LIMIT $1
                """,
                limit,
            )
        return [dict(r) for r in rows]

    async def update_artifact_gate1(
        self, artifact_id: UUID, faithfulness_score: float
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_dream_artifacts SET faithfulness_score = $2 WHERE id = $1",
                artifact_id,
                faithfulness_score,
            )

    async def update_artifact_gate2(
        self, artifact_id: UUID, novelty_score: float
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_dream_artifacts SET novelty_score = $2 WHERE id = $1",
                artifact_id,
                novelty_score,
            )

    async def update_artifact_gate3(self, artifact_id: UUID, retrievable: bool) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_dream_artifacts SET retrievable = $2 WHERE id = $1",
                artifact_id,
                retrievable,
            )

    async def update_artifact_critics(
        self,
        artifact_id: UUID,
        critic_a_verdict: str,
        critic_a_reason: str | None,
        critic_b_verdict: str,
        critic_b_reason: str | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_dream_artifacts SET
                    critic_a_verdict = $2,
                    critic_a_reason  = $3,
                    critic_b_verdict = $4,
                    critic_b_reason  = $5
                WHERE id = $1
                """,
                artifact_id,
                critic_a_verdict,
                critic_a_reason,
                critic_b_verdict,
                critic_b_reason,
            )

    async def mark_artifact_promoted(
        self,
        artifact_id: UUID,
        promoted_to: str | None = None,
        promoted_id: UUID | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_dream_artifacts SET
                    status      = 'promoted',
                    promoted_to = $2,
                    promoted_id = $3
                WHERE id = $1
                """,
                artifact_id,
                promoted_to,
                promoted_id,
            )

    async def mark_artifact_reviewed(self, artifact_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_dream_artifacts SET reviewed_at = now() WHERE id = $1",
                artifact_id,
            )

    async def set_revised_content(self, artifact_id: UUID, content: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE memory_dream_artifacts SET
                    user_revised_content = $2,
                    status = 'revised'
                WHERE id = $1
                """,
                artifact_id,
                content,
            )

    async def get_last_successful_run_at(self) -> datetime | None:
        """Return finished_at of the most recent dream run that completed without error."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT finished_at FROM memory_dream_runs
                WHERE finished_at IS NOT NULL AND error IS NULL
                ORDER BY finished_at DESC
                LIMIT 1
                """
            )
        return row["finished_at"] if row else None

    async def count_artifacts_by_status(self, run_id: UUID) -> dict[str, int]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT status, count(*) AS n
                FROM memory_dream_artifacts
                WHERE run_id = $1
                GROUP BY status
                """,
                run_id,
            )
        return {r["status"]: r["n"] for r in rows}
