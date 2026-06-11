from __future__ import annotations

from datetime import datetime
from typing import Any

import asyncpg

from ze_api.logging import get_logger

log = get_logger(__name__)


class PendingConfirmationStore:
    """Persists in-flight confirm_request payloads so they survive reconnects."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(
        self,
        thread_id: str,
        request_id: str,
        prompt: str,
        actions: list[dict],
        expires_at: datetime,
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO pending_confirmations
                        (thread_id, request_id, prompt, actions, expires_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (thread_id) DO UPDATE
                        SET request_id = EXCLUDED.request_id,
                            prompt     = EXCLUDED.prompt,
                            actions    = EXCLUDED.actions,
                            expires_at = EXCLUDED.expires_at,
                            created_at = now()
                    """,
                    thread_id,
                    request_id,
                    prompt,
                    actions,
                    expires_at,
                )
        except Exception as exc:
            log.warning("confirmation_save_failed", error=str(exc))

    async def get_any_pending(self) -> dict | None:
        """Return any non-expired pending confirmation, or None."""
        try:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM pending_confirmations WHERE expires_at > NOW() LIMIT 1"
                )
            if row is None:
                return None
            return {
                "thread_id": row["thread_id"],
                "request_id": row["request_id"],
                "prompt": row["prompt"],
                "actions": row["actions"],
            }
        except Exception as exc:
            log.warning("confirmation_get_failed", error=str(exc))
            return None

    async def clear(self, thread_id: str) -> bool:
        """Delete the row for thread_id. Returns True if a row was deleted."""
        try:
            async with self._pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM pending_confirmations WHERE thread_id = $1",
                    thread_id,
                )
            return result == "DELETE 1"
        except Exception as exc:
            log.warning("confirmation_clear_failed", error=str(exc))
            return False
