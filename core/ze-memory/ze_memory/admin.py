from __future__ import annotations

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
                await conn.execute("DELETE FROM user_facts WHERE id = $1", action.id)
            elif action.action == "confirm":
                row = await conn.fetchrow(
                    "UPDATE user_facts SET reviewed = true, expires_at = NULL WHERE id = $1 RETURNING *",
                    action.id,
                )
                if row:
                    updated.append(dict(row))
            elif action.action == "edit":
                row = await conn.fetchrow(
                    "UPDATE user_facts SET value = $1, reviewed = true WHERE id = $2 RETURNING *",
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
