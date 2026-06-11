from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from ze_core.db import DBPool
from ze_core.logging import get_logger
from ze_personal.goals.types import GoalSuggestion, SuggestionStatus

log = get_logger(__name__)


def _suggestion_from_row(row) -> GoalSuggestion:
    return GoalSuggestion(
        id=row["id"],
        title=row["title"],
        objective=row["objective"],
        rationale=row["rationale"],
        source_type=row["source_type"],
        source_ref=row["source_ref"],
        status=SuggestionStatus(row["status"]),
        suggested_at=row["suggested_at"],
        resolved_at=row["resolved_at"],
        created_goal_id=row["created_goal_id"],
    )


class GoalSuggestionStore:
    def __init__(self, pool: DBPool) -> None:
        self._pool = pool

    async def save(self, suggestion: GoalSuggestion, week_key: str) -> bool:
        """
        Persist a new suggestion. Returns True on success, False if week_key already
        exists (unique violation → another job instance already saved this week's suggestion).
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO goal_suggestions
                    (id, title, objective, rationale, source_type, source_ref,
                     status, week_key, suggested_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (week_key) DO NOTHING
                RETURNING id
                """,
                suggestion.id,
                suggestion.title,
                suggestion.objective,
                suggestion.rationale,
                suggestion.source_type,
                suggestion.source_ref,
                suggestion.status.value,
                week_key,
                suggestion.suggested_at,
            )
            return row is not None

    async def get(self, suggestion_id: UUID) -> GoalSuggestion | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM goal_suggestions WHERE id = $1",
                suggestion_id,
            )
            return _suggestion_from_row(row) if row else None

    async def mark_accepted(self, suggestion_id: UUID, goal_id: UUID) -> bool:
        """
        Atomically transitions status from PENDING → ACCEPTED.
        Returns True if the row was updated, False if already resolved.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE goal_suggestions
                SET status = 'accepted', resolved_at = now(), created_goal_id = $2
                WHERE id = $1 AND status = 'pending'
                RETURNING id
                """,
                suggestion_id,
                goal_id,
            )
            return row is not None

    async def mark_dismissed(self, suggestion_id: UUID) -> bool:
        """Atomically transitions status from PENDING → DISMISSED. Returns False if already resolved."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE goal_suggestions
                SET status = 'dismissed', resolved_at = now()
                WHERE id = $1 AND status = 'pending'
                RETURNING id
                """,
                suggestion_id,
            )
            return row is not None

    async def mark_expired(self, suggestion_id: UUID) -> None:
        """Unconditional status update to EXPIRED."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE goal_suggestions SET status = 'expired', resolved_at = now() WHERE id = $1",
                suggestion_id,
            )

    async def expire_stale_pending(self, older_than_days: int = 30) -> int:
        """
        Mark as EXPIRED any PENDING suggestions older than `older_than_days`.
        Returns the number of rows updated.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE goal_suggestions
                SET status = 'expired', resolved_at = now()
                WHERE status = 'pending' AND suggested_at < $1
                """,
                cutoff,
            )
            # asyncpg returns "UPDATE N" as the status string
            count = int(result.split()[-1])
            return count

    async def was_suggested_recently(self, days: int = 30) -> bool:
        """
        Returns True if any non-EXPIRED suggestion was saved within the last `days` days.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM goal_suggestions
                WHERE status IN ('pending', 'accepted', 'dismissed')
                  AND suggested_at >= $1
                LIMIT 1
                """,
                cutoff,
            )
            return row is not None

    async def was_topic_suggested_recently(self, title: str, days: int = 30) -> bool:
        """
        Returns True if a suggestion with a similar title (case-insensitive substring match)
        was sent within the last `days` days, excluding EXPIRED suggestions.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM goal_suggestions
                WHERE status != 'expired'
                  AND suggested_at >= $1
                  AND LOWER(title) LIKE '%' || LOWER($2) || '%'
                LIMIT 1
                """,
                cutoff,
                title,
            )
            return row is not None

    async def resolve_short_id(self, short_id: str) -> GoalSuggestion | None:
        """
        Finds a suggestion whose UUID starts with `short_id` (8 hex chars).
        Returns None if multiple PENDING suggestions share the prefix (collision guard).
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM goal_suggestions
                WHERE id::text LIKE $1
                ORDER BY
                    CASE WHEN status = 'pending' THEN 0 ELSE 1 END,
                    suggested_at DESC
                """,
                f"{short_id}%",
            )
            if not rows:
                return None
            pending = [r for r in rows if r["status"] == "pending"]
            if len(pending) > 1:
                log.warning("goal_suggestion_short_id_collision", short_id=short_id, count=len(pending))
                return None
            if pending:
                return _suggestion_from_row(pending[0])
            return _suggestion_from_row(rows[0])
