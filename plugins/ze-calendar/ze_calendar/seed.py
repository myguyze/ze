from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids
from ze_seed.narrative.ids import REMINDER_IDS


async def _clear_calendar(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "user_reminders", REMINDER_IDS)


async def _apply_calendar(ctx: SeedContext) -> int:
    if ctx.narrative is None:
        return 0
    count = 0
    now = datetime.now(timezone.utc)
    async with ctx.pool.acquire() as conn:
        for reminder in ctx.narrative.reminders:
            fire_at = now + timedelta(days=reminder.days_from_now)
            await conn.execute(
                """
                INSERT INTO user_reminders (id, label, fire_at, sent)
                VALUES ($1, $2, $3, false)
                ON CONFLICT (id) DO NOTHING
                """,
                reminder.id,
                reminder.label,
                fire_at,
            )
            count += 1
    return count


def calendar_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain(
            "calendar.dev", seed_order=28, clear=_clear_calendar, apply=_apply_calendar
        ),
    ]
