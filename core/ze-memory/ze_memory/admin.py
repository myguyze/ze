from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def _aliases_from_row(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (ValueError, TypeError):
            return []
    return []


def _attrs_from_row(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


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
    as_of: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    if before is None:
        before = now
    snapshot = as_of if as_of is not None else now

    async with pool.acquire() as conn:
        if as_of is not None:
            totals = await conn.fetchrow(
                """
                SELECT
                    (SELECT COUNT(*) FROM memory_facts
                     WHERE created_at <= $1
                       AND (expires_at IS NULL OR expires_at > $1)
                       AND NOT (contradicted = true AND updated_at <= $1)
                    ) AS total_facts,
                    (SELECT COUNT(*) FROM memory_episodes WHERE created_at <= $1) AS total_episodes
                """,
                snapshot,
            )
        else:
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
              AND created_at <= $5
              AND ($2::TEXT IS NULL OR agent = $2)
              AND ($3 = 'all' OR $3 = 'fact')
              AND (expires_at IS NULL OR expires_at > $5)
              AND NOT (contradicted = true AND updated_at <= $5)

            UNION ALL

            SELECT id, 'episode' AS type,
                   NULL::TEXT AS key, NULL::TEXT AS value, NULL::FLOAT8 AS confidence,
                   NULL::BOOLEAN AS reviewed, NULL::BOOLEAN AS contradicted,
                   NULL::TEXT AS provenance, summary, LEFT(prompt, 120) AS prompt_snippet,
                   agent, created_at
            FROM memory_episodes
            WHERE created_at < $1
              AND created_at <= $5
              AND ($2::TEXT IS NULL OR agent = $2)
              AND ($3 = 'all' OR $3 = 'episode')

            ORDER BY created_at DESC
            LIMIT $4
            """,
            before, agent_filter, type_filter, limit, snapshot,
        )

    items = [dict(r) for r in rows]
    next_before = items[-1]["created_at"] if len(items) >= limit else None
    return {
        "items": items,
        "next_before": next_before,
        "total_facts": totals["total_facts"],
        "total_episodes": totals["total_episodes"],
    }


async def get_memory_timeline_bounds(pool: Any) -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT MIN(ts) AS earliest
            FROM (
                SELECT MIN(created_at) AS ts FROM memory_facts
                UNION ALL
                SELECT MIN(created_at) AS ts FROM memory_episodes
            ) sub
            """
        )
    return {
        "earliest": row["earliest"],
        "latest": datetime.now(timezone.utc),
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


async def get_memory_graph(
    pool: Any,
    limit: int = 50,
    entity_type: str | None = None,
    seed_id: Any | None = None,
) -> dict:
    async with pool.acquire() as conn:
        if seed_id is not None:
            # Expand 1-hop from the seed entity.
            rows = await conn.fetch(
                """
                SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
                       COUNT(r.id) AS degree
                FROM memory_entities e
                LEFT JOIN memory_relationships r
                  ON r.source_id = e.id OR r.target_id = e.id
                WHERE e.id = $1
                   OR e.id IN (
                       SELECT target_id FROM memory_relationships
                       WHERE source_id = $1 AND target_id IS NOT NULL AND target_type = 'entity'
                       UNION
                       SELECT source_id FROM memory_relationships
                       WHERE target_id = $1 AND source_type = 'entity'
                   )
                GROUP BY e.id
                LIMIT $2
                """,
                seed_id, limit,
            )
        elif entity_type is not None:
            rows = await conn.fetch(
                """
                SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
                       COUNT(r.id) AS degree
                FROM memory_entities e
                LEFT JOIN memory_relationships r
                  ON r.source_id = e.id OR r.target_id = e.id
                WHERE e.entity_type = $1
                GROUP BY e.id
                ORDER BY degree DESC
                LIMIT $2
                """,
                entity_type, limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
                       COUNT(r.id) AS degree
                FROM memory_entities e
                LEFT JOIN memory_relationships r
                  ON r.source_id = e.id OR r.target_id = e.id
                GROUP BY e.id
                ORDER BY degree DESC
                LIMIT $1
                """,
                limit,
            )

        entity_ids = [r["id"] for r in rows]
        nodes = [
            {
                "id": r["id"],
                "entity_type": r["entity_type"],
                "canonical_name": r["canonical_name"],
                "aliases": _aliases_from_row(r["aliases"]),
                "attrs": _attrs_from_row(r["attrs"]),
                "degree": r["degree"],
            }
            for r in rows
        ]

        if not entity_ids:
            return {"nodes": [], "edges": []}

        edge_rows = await conn.fetch(
            """
            SELECT id, source_id, target_id, predicate, confidence
            FROM memory_relationships
            WHERE source_type = 'entity'
              AND target_type = 'entity'
              AND source_id = ANY($1)
              AND target_id = ANY($1)
            """,
            entity_ids,
        )
        edges = [
            {
                "id": r["id"],
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "predicate": r["predicate"],
                "confidence": r["confidence"],
            }
            for r in edge_rows
        ]

    return {"nodes": nodes, "edges": edges}


async def get_entity_detail(pool: Any, entity_id: Any) -> dict | None:
    async with pool.acquire() as conn:
        entity_row = await conn.fetchrow(
            """
            SELECT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
                   COUNT(r.id) AS degree
            FROM memory_entities e
            LEFT JOIN memory_relationships r
              ON r.source_id = e.id OR r.target_id = e.id
            WHERE e.id = $1
            GROUP BY e.id
            """,
            entity_id,
        )
        if entity_row is None:
            return None

        entity = {
            "id": entity_row["id"],
            "entity_type": entity_row["entity_type"],
            "canonical_name": entity_row["canonical_name"],
            "aliases": _aliases_from_row(entity_row["aliases"]),
            "attrs": _attrs_from_row(entity_row["attrs"]),
            "degree": entity_row["degree"],
        }

        fact_rows = await conn.fetch(
            """
            SELECT f.id, f.predicate AS key, f.value, COALESCE(me.agent, 'unknown') AS agent
            FROM memory_facts f
            LEFT JOIN memory_episodes me ON me.id = f.source_episode_id
            WHERE f.subject_id = $1
            ORDER BY f.created_at DESC
            LIMIT 20
            """,
            entity_id,
        )
        facts = [
            {"id": r["id"], "key": r["key"], "value": r["value"], "agent": r["agent"]}
            for r in fact_rows
        ]

        episode_rows = await conn.fetch(
            """
            SELECT DISTINCT me.id, me.agent,
                   me.summary, me.created_at
            FROM memory_episodes me
            JOIN memory_facts f ON f.source_episode_id = me.id
            WHERE f.subject_id = $1
            ORDER BY me.created_at DESC
            LIMIT 10
            """,
            entity_id,
        )
        episodes = [
            {"id": r["id"], "agent": r["agent"], "summary": r["summary"], "created_at": r["created_at"]}
            for r in episode_rows
        ]

        neighbour_rows = await conn.fetch(
            """
            SELECT DISTINCT e.id, e.entity_type, e.canonical_name, e.aliases, e.attrs,
                   COUNT(r2.id) AS degree
            FROM memory_relationships r
            JOIN memory_entities e
              ON (r.target_id = e.id AND r.source_id = $1)
              OR (r.source_id = e.id AND r.target_id = $1)
            LEFT JOIN memory_relationships r2 ON r2.source_id = e.id OR r2.target_id = e.id
            WHERE (r.source_id = $1 OR r.target_id = $1)
              AND (
                (r.source_id = $1 AND r.target_type = 'entity')
                OR (r.target_id = $1 AND r.source_type = 'entity')
              )
            GROUP BY e.id
            LIMIT 20
            """,
            entity_id,
        )
        neighbour_ids = [r["id"] for r in neighbour_rows]
        neighbours = [
            {
                "id": r["id"],
                "entity_type": r["entity_type"],
                "canonical_name": r["canonical_name"],
                "aliases": _aliases_from_row(r["aliases"]),
                "attrs": _attrs_from_row(r["attrs"]),
                "degree": r["degree"],
            }
            for r in neighbour_rows
        ]

        neighbour_edge_rows: list = []
        if neighbour_ids:
            all_ids = [entity_id] + neighbour_ids
            neighbour_edge_rows = await conn.fetch(
                """
                SELECT id, source_id, target_id, predicate, confidence
                FROM memory_relationships
                WHERE source_type = 'entity'
                  AND target_type = 'entity'
                  AND (source_id = $1 OR target_id = $1)
                  AND source_id = ANY($2)
                  AND target_id = ANY($2)
                """,
                entity_id, all_ids,
            )
        neighbour_edges = [
            {
                "id": r["id"],
                "source_id": r["source_id"],
                "target_id": r["target_id"],
                "predicate": r["predicate"],
                "confidence": r["confidence"],
            }
            for r in neighbour_edge_rows
        ]

    return {
        "entity": entity,
        "facts": facts,
        "episodes": episodes,
        "neighbours": neighbours,
        "neighbour_edges": neighbour_edges,
    }
