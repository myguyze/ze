from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

import asyncpg

from ze_core.logging import get_logger

log = get_logger(__name__)


@dataclass
class CalendarReminder:
    id: UUID
    event_id: str
    event_title: str
    fire_at: datetime
    label: str
    sent: bool
    assessed_at: datetime


class CalendarReminderStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_unsent(self) -> list[CalendarReminder]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, event_id, event_title, fire_at, label, sent, assessed_at "
                "FROM calendar_reminders WHERE sent = false AND fire_at > NOW() ORDER BY fire_at"
            )
        return [_to_reminder(r) for r in rows]

    async def list_for_event(self, event_id: str) -> list[CalendarReminder]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, event_id, event_title, fire_at, label, sent, assessed_at "
                "FROM calendar_reminders WHERE event_id = $1",
                event_id,
            )
        return [_to_reminder(r) for r in rows]

    async def create(
        self,
        event_id: str,
        event_title: str,
        fire_at: datetime,
        label: str,
    ) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO calendar_reminders (event_id, event_title, fire_at, label)
                VALUES ($1, $2, $3, $4) RETURNING id
                """,
                event_id, event_title, fire_at, label,
            )
        return row["id"]

    async def mark_sent(self, reminder_id: UUID) -> str | None:
        """Atomically mark sent. Returns the label if claimed, None if already sent."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE calendar_reminders SET sent = true, sent_at = NOW() "
                "WHERE id = $1 AND sent = false RETURNING label",
                reminder_id,
            )
        return row["label"] if row else None

    async def delete_unsent_for_event(self, event_id: str) -> list[UUID]:
        """Delete unsent reminders for an event (e.g. when event is updated). Returns deleted IDs."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "DELETE FROM calendar_reminders WHERE event_id = $1 AND sent = false RETURNING id",
                event_id,
            )
        return [r["id"] for r in rows]


def _to_reminder(row) -> CalendarReminder:
    return CalendarReminder(
        id=row["id"],
        event_id=row["event_id"],
        event_title=row["event_title"],
        fire_at=row["fire_at"],
        label=row["label"],
        sent=row["sent"],
        assessed_at=row["assessed_at"],
    )
