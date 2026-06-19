from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any
from uuid import UUID

from ze_onboarding.types import (
    OnboardingSeed,
    OnboardingStep,
    OnboardingSession,
    OnboardingStoredStepStatus,
    StoredOnboardingSeed,
    StoredOnboardingStep,
)


def _json_load(value: Any) -> Any:
    if isinstance(value, str):
        return json.loads(value)
    return value


class OnboardingStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get_active_session(self) -> OnboardingSession | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, status, started_at, completed_at
                FROM onboarding_sessions
                WHERE status = 'active'
                ORDER BY started_at DESC
                LIMIT 1
                """
            )
        return _row_to_session(row) if row is not None else None

    async def has_completed_session(self) -> bool:
        async with self._pool.acquire() as conn:
            exists = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM onboarding_sessions
                    WHERE status = 'completed'
                )
                """
            )
        return bool(exists)

    async def create_session(self) -> OnboardingSession:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO onboarding_sessions DEFAULT VALUES
                RETURNING id, status, started_at, completed_at
                """
            )
        return _row_to_session(row)

    async def complete_session(self, session_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_sessions
                SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                WHERE id = $1
                """,
                session_id,
            )

    async def upsert_steps(self, session_id: UUID, steps: list[OnboardingStep]) -> None:
        async with self._pool.acquire() as conn:
            for idx, step in enumerate(steps):
                status: OnboardingStoredStepStatus = "active" if idx == 0 else "pending"
                await conn.execute(
                    """
                    INSERT INTO onboarding_steps
                      (session_id, plugin, step_key, status, descriptor)
                    VALUES ($1, $2, $3, $4, $5::jsonb)
                    ON CONFLICT (session_id, plugin, step_key) DO UPDATE SET
                      descriptor = EXCLUDED.descriptor
                    """,
                    session_id,
                    step.plugin,
                    step.id,
                    status,
                    json.dumps(_step_to_descriptor(step)),
                )

    async def get_current_step(self, session_id: UUID) -> StoredOnboardingStep | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, plugin, step_key, status, descriptor, submission, completed_at
                FROM onboarding_steps
                WHERE session_id = $1 AND status IN ('active', 'pending')
                ORDER BY
                  CASE status WHEN 'active' THEN 0 ELSE 1 END,
                  created_at ASC
                LIMIT 1
                """,
                session_id,
            )
        return _row_to_step(row) if row is not None else None

    async def get_step_by_key(
        self,
        session_id: UUID,
        step_key: str,
    ) -> StoredOnboardingStep | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, plugin, step_key, status, descriptor, submission, completed_at
                FROM onboarding_steps
                WHERE session_id = $1 AND step_key = $2
                """,
                session_id,
                step_key,
            )
        return _row_to_step(row) if row is not None else None

    async def complete_step(
        self,
        step: StoredOnboardingStep,
        submission: dict[str, Any],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'completed', submission = $2::jsonb, completed_at = NOW()
                WHERE id = $1
                """,
                step.id,
                json.dumps(submission),
            )
            await conn.execute(
                """
                UPDATE onboarding_steps
                SET status = 'active'
                WHERE id = (
                    SELECT id
                    FROM onboarding_steps
                    WHERE session_id = $1 AND status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                )
                """,
                step.session_id,
            )

    async def insert_steps_after_current(
        self,
        session_id: UUID,
        steps: list[OnboardingStep],
    ) -> None:
        if not steps:
            return
        async with self._pool.acquire() as conn:
            for step in steps:
                await conn.execute(
                    """
                    INSERT INTO onboarding_steps
                      (session_id, plugin, step_key, status, descriptor)
                    VALUES ($1, $2, $3, 'pending', $4::jsonb)
                    ON CONFLICT (session_id, plugin, step_key) DO UPDATE SET
                      descriptor = EXCLUDED.descriptor
                    """,
                    session_id,
                    step.plugin,
                    step.id,
                    json.dumps(_step_to_descriptor(step)),
                )

    async def insert_seeds(
        self,
        session_id: UUID,
        step_id: UUID | None,
        seeds: list[OnboardingSeed],
    ) -> None:
        if not seeds:
            return
        async with self._pool.acquire() as conn:
            for seed in seeds:
                await conn.execute(
                    """
                    INSERT INTO onboarding_seeds
                      (session_id, step_id, plugin, kind, key, value, confidence, review_status)
                    VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
                    """,
                    session_id,
                    step_id,
                    seed.plugin,
                    seed.kind,
                    seed.key,
                    json.dumps(seed.value),
                    seed.confidence,
                    "pending" if seed.review_required else "approved",
                )

    async def list_pending_seeds(self, session_id: UUID) -> list[StoredOnboardingSeed]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, step_id, plugin, kind, key, value, confidence, review_status
                FROM onboarding_seeds
                WHERE session_id = $1 AND review_status = 'pending'
                ORDER BY created_at ASC
                """,
                session_id,
            )
        return [_row_to_seed(row) for row in rows]

    async def approve_pending_seeds(self, session_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_seeds
                SET review_status = 'approved'
                WHERE session_id = $1 AND review_status = 'pending'
                """,
                session_id,
            )

    async def reset_for_edit(self, session_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE onboarding_seeds
                    SET review_status = 'rejected'
                    WHERE session_id = $1 AND review_status = 'pending'
                    """,
                    session_id,
                )
                await conn.execute(
                    """
                    UPDATE onboarding_steps
                    SET status = 'pending', submission = NULL, completed_at = NULL
                    WHERE session_id = $1 AND status = 'completed'
                    """,
                    session_id,
                )
                await conn.execute(
                    """
                    UPDATE onboarding_steps
                    SET status = 'active'
                    WHERE id = (
                        SELECT id
                        FROM onboarding_steps
                        WHERE session_id = $1 AND status = 'pending'
                        ORDER BY created_at ASC
                        LIMIT 1
                    )
                    """,
                    session_id,
                )

    async def list_approved_seeds(self, session_id: UUID) -> list[StoredOnboardingSeed]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, step_id, plugin, kind, key, value, confidence, review_status
                FROM onboarding_seeds
                WHERE session_id = $1 AND review_status = 'approved'
                ORDER BY created_at ASC
                """,
                session_id,
            )
        return [_row_to_seed(row) for row in rows]

    async def mark_seeds_applied(self, seed_ids: list[UUID]) -> None:
        if not seed_ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE onboarding_seeds
                SET review_status = 'applied', applied_at = NOW()
                WHERE id = ANY($1)
                """,
                seed_ids,
            )


def _step_to_descriptor(step: OnboardingStep) -> dict[str, Any]:
    data = asdict(step)
    data["type"] = step.kind
    data["id"] = step.id
    return data


def _row_to_session(row: Any) -> OnboardingSession:
    return OnboardingSession(
        id=row["id"],
        status=row["status"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
    )


def _row_to_step(row: Any) -> StoredOnboardingStep:
    return StoredOnboardingStep(
        id=row["id"],
        session_id=row["session_id"],
        plugin=row["plugin"],
        step_key=row["step_key"],
        status=row["status"],
        descriptor=_json_load(row["descriptor"]),
        submission=_json_load(row["submission"]) if row["submission"] is not None else None,
        completed_at=row["completed_at"],
    )


def _row_to_seed(row: Any) -> StoredOnboardingSeed:
    return StoredOnboardingSeed(
        id=row["id"],
        session_id=row["session_id"],
        step_id=row["step_id"],
        plugin=row["plugin"],
        kind=row["kind"],
        key=row["key"],
        value=_json_load(row["value"]),
        confidence=float(row["confidence"]),
        review_status=row["review_status"],
    )
