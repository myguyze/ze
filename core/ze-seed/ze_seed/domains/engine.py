from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ze_core.conversation.messages.types import Message
from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids
from ze_seed.narrative.ids import MESSAGE_IDS, ONBOARDING_SESSION_ID, SEED_SESSION_ID


async def _clear_engine(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "messages", MESSAGE_IDS)
        await conn.execute("DELETE FROM sessions WHERE id = $1", SEED_SESSION_ID)
        await conn.execute(
            "DELETE FROM onboarding_seeds WHERE session_id = $1", ONBOARDING_SESSION_ID
        )
        await conn.execute(
            "DELETE FROM onboarding_steps WHERE session_id = $1", ONBOARDING_SESSION_ID
        )
        await conn.execute(
            "DELETE FROM onboarding_sessions WHERE id = $1", ONBOARDING_SESSION_ID
        )


async def _apply_engine(ctx: SeedContext) -> int:
    if ctx.narrative is None:
        return 0
    count = 0
    now = datetime.now(timezone.utc)

    await ctx.session_store.create(SEED_SESSION_ID, title="Dev seed chat")

    for i, msg_spec in enumerate(ctx.narrative.messages):
        day_offset = timedelta(days=msg_spec.days_ago)
        minute_offset = timedelta(minutes=i * 3)
        created_at = now - day_offset + minute_offset
        message = Message(
            id=msg_spec.id,
            role=msg_spec.role,  # type: ignore[arg-type]
            text=msg_spec.text,
            components=[],
            read=True,
            created_at=created_at,
            thread_id=SEED_SESSION_ID,
        )
        await ctx.message_store.save(message)
        if msg_spec.trace is not None:
            await ctx.message_store.save_trace(msg_spec.id, msg_spec.trace)
        count += 1

    async with ctx.pool.acquire() as conn:
        completed_at = now - timedelta(days=30)
        await conn.execute(
            """
            INSERT INTO onboarding_sessions (id, status, started_at, completed_at)
            VALUES ($1, 'completed', $2, $3)
            ON CONFLICT (id) DO NOTHING
            """,
            ONBOARDING_SESSION_ID,
            completed_at - timedelta(hours=1),
            completed_at,
        )
        await conn.execute(
            """
            INSERT INTO onboarding_seeds
                (session_id, plugin, kind, key, value, confidence, review_status)
            VALUES ($1, 'ze_personal', 'profile_facet', 'communication_style', $2, 1.0, 'applied')
            """,
            ONBOARDING_SESSION_ID,
            json.dumps(ctx.narrative.communication_style),
        )
        count += 2

    return count


def engine_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain("engine.dev", seed_order=25, clear=_clear_engine, apply=_apply_engine),
    ]
