from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from ze_core.logging import get_logger

log = get_logger(__name__)


@dataclass
class PushLogEntry:
    event_type: str
    payload: str | None
    sent_at: datetime


class PushLogStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def was_sent_within_hours(self, event_type: str, hours: float) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM push_log WHERE event_type = $1 "
                "AND sent_at > NOW() - ($2 * INTERVAL '1 hour')",
                event_type,
                hours,
            )
        return row is not None

    async def log(self, event_type: str, payload: str | None = None) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO push_log (event_type, payload) VALUES ($1, $2)",
                event_type,
                payload,
            )
        log.debug("push_log_recorded", event_type=event_type)

    async def list_workflow_failures_within_hours(
        self, hours: int = 24
    ) -> list[PushLogEntry]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT event_type, payload, sent_at FROM push_log "
                "WHERE event_type LIKE 'workflow_failure:%' "
                "AND sent_at > NOW() - ($1 * INTERVAL '1 hour') "
                "ORDER BY sent_at DESC",
                hours,
            )
        return [
            PushLogEntry(
                event_type=r["event_type"],
                payload=r["payload"],
                sent_at=r["sent_at"],
            )
            for r in rows
        ]
