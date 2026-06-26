from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


async def list_facts(pool: Any) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at "
            "FROM user_facts ORDER BY updated_at DESC"
        )
    return [dict(r) for r in rows]


async def review_facts(pool: Any, actions: list[Any]) -> list[dict]:
    updated: list[dict] = []
    async with pool.acquire() as conn:
        for action in actions:
            if action.action == "reject":
                await conn.execute("DELETE FROM memory_facts WHERE id = $1", action.id)
            elif action.action == "confirm":
                row = await conn.fetchrow(
                    "UPDATE memory_facts SET reviewed = true WHERE id = $1"
                    " RETURNING id, 'fact' AS type, predicate AS key, value, confidence, reviewed,"
                    " contradicted, provenance, NULL::TEXT AS summary, NULL::TEXT AS prompt_snippet,"
                    " agent, created_at",
                    action.id,
                )
                if row:
                    updated.append(dict(row))
            elif action.action == "edit":
                row = await conn.fetchrow(
                    "UPDATE memory_facts SET value = $1, reviewed = true WHERE id = $2"
                    " RETURNING id, 'fact' AS type, predicate AS key, value, confidence, reviewed,"
                    " contradicted, provenance, NULL::TEXT AS summary, NULL::TEXT AS prompt_snippet,"
                    " agent, created_at",
                    action.value,
                    action.id,
                )
                if row:
                    updated.append(dict(row))
    return updated


async def get_memory_digest(pool: Any) -> dict:
    async with pool.acquire() as conn:
        unreviewed = await conn.fetch(
            "SELECT id, key, value, agent FROM user_facts WHERE reviewed = false ORDER BY updated_at DESC"
        )
        contradicted = await conn.fetch(
            "SELECT id, key, value, agent FROM user_facts WHERE contradicted = true ORDER BY updated_at DESC"
        )
        episodes = await conn.fetch(
            "SELECT id, agent, summary, created_at FROM episodes ORDER BY created_at DESC LIMIT 10"
        )
        expiring = await conn.fetch(
            "SELECT id, key, value, agent, expires_at FROM user_facts "
            "WHERE expires_at IS NOT NULL AND expires_at > NOW() ORDER BY expires_at ASC"
        )
    return {
        "unreviewed_facts": [dict(r) for r in unreviewed],
        "contradicted_facts": [dict(r) for r in contradicted],
        "recent_episodes": [dict(r) for r in episodes],
        "expiring_facts": [dict(r) for r in expiring],
    }


async def get_memory_feed(
    pool: Any,
    limit: int = 50,
    before: datetime | None = None,
    type_filter: str = "all",
    agent_filter: str | None = None,
) -> dict:
    if before is None:
        before = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            "SELECT (SELECT COUNT(*) FROM memory_facts) AS total_facts,"
            " (SELECT COUNT(*) FROM memory_episodes) AS total_episodes"
        )
        rows = await conn.fetch(
            """
            SELECT id, 'fact' AS type,
                   predicate AS key, value, confidence, reviewed, contradicted,
                   provenance, NULL::TEXT AS summary, NULL::TEXT AS prompt_snippet,
                   agent, created_at
            FROM memory_facts
            WHERE created_at < $1
              AND ($2::TEXT IS NULL OR agent = $2)
              AND ($3 = 'all' OR $3 = 'fact')

            UNION ALL

            SELECT id, 'episode' AS type,
                   NULL::TEXT AS key, NULL::TEXT AS value, NULL::FLOAT8 AS confidence,
                   NULL::BOOLEAN AS reviewed, NULL::BOOLEAN AS contradicted,
                   NULL::TEXT AS provenance, summary, LEFT(prompt, 120) AS prompt_snippet,
                   agent, created_at
            FROM memory_episodes
            WHERE created_at < $1
              AND ($2::TEXT IS NULL OR agent = $2)
              AND ($3 = 'all' OR $3 = 'episode')

            ORDER BY created_at DESC
            LIMIT $4
            """,
            before, agent_filter, type_filter, limit,
        )

    items = [dict(r) for r in rows]
    next_before = items[-1]["created_at"] if len(items) >= limit else None
    return {
        "items": items,
        "next_before": next_before,
        "total_facts": totals["total_facts"],
        "total_episodes": totals["total_episodes"],
    }


async def get_profile(pool: Any) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT preferences, habits, topics, relationships, goals, updated_at, version "
            "FROM user_profile WHERE id = 1"
        )
    if row is None:
        return None
    if not any([
        row["preferences"], row["habits"], row["topics"],
        row["relationships"], row["goals"],
    ]):
        return None
    return dict(row)
