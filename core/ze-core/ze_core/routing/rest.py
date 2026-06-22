from __future__ import annotations

from typing import Any


async def list_routing_log(pool: Any, *, limit: int, offset: int) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, session_id, prompt, method, primary_agent,
                   confidence, score_gap, is_compound, raw_scores,
                   created_at::text AS created_at
            FROM routing_log
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit,
            offset,
        )
    return [dict(r) for r in rows]
