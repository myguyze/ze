"""PostgresConsolidationStore — DB operations used exclusively by MemoryConsolidator.

Separated from PostgresMemoryStore to keep the runtime store focused on the
read/write protocol and to give consolidation jobs a minimal, clearly bounded
dependency.
"""
from __future__ import annotations

import json
from typing import Any


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _as_float_vector(embedding: Any) -> list[float]:
    if embedding is None:
        return []
    if hasattr(embedding, "tolist"):
        vals = embedding.tolist()
    elif isinstance(embedding, str):
        text = embedding.strip()
        if not text.startswith("["):
            return []
        vals = json.loads(text)
    else:
        vals = list(embedding)
    return [float(x) for x in vals]


def _cosine_similarity(a: Any, b: Any) -> float:
    a_l = _as_float_vector(a)
    b_l = _as_float_vector(b)
    if not a_l or not b_l:
        return 0.0
    dot = sum(x * y for x, y in zip(a_l, b_l))
    norm_a = sum(x * x for x in a_l) ** 0.5
    norm_b = sum(y * y for y in b_l) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _parse_update_count(status: Any) -> int:
    try:
        return int(str(status).split()[-1])
    except (ValueError, IndexError):
        return 0


class PostgresConsolidationStore:
    """Read/write store for MemoryConsolidator — pool-only, no embedder or LLM client."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    # ── fact maintenance ──────────────────────────────────────────────────────

    async def fetch_active_facts(self) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, predicate, value, confidence, created_at"
                " FROM memory_facts WHERE contradicted = false ORDER BY updated_at DESC"
            )

    async def mark_contradicted(self, fact_id: Any) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE memory_facts SET contradicted = true WHERE id = $1", fact_id
            )

    async def insert_merged_fact(
        self,
        predicate: str,
        value: str,
        confidence: float,
        embedding: Any,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO memory_facts (predicate, value, confidence, embedding, agent)"
                " VALUES ($1, $2, $3, $4::vector, 'consolidation')",
                predicate,
                value,
                confidence,
                _to_list(embedding),
            )

    async def soft_expire_unreviewed_facts(self, ttl_days: int, grace_days: int) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE memory_facts"
                " SET expires_at = NOW() + $1::interval"
                " WHERE reviewed = false AND contradicted = false"
                " AND expires_at IS NULL"
                " AND updated_at < NOW() - $2::interval",
                f"{grace_days} days",
                f"{ttl_days} days",
            )
        return _parse_update_count(result)

    async def delete_expired_facts(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memory_facts WHERE expires_at IS NOT NULL AND expires_at < NOW()"
            )
        return _parse_update_count(result)

    async def delete_contradicted_facts(self, ttl_days: int) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memory_facts WHERE contradicted = true"
                " AND updated_at < NOW() - $1::interval",
                f"{ttl_days} days",
            )
        return _parse_update_count(result)

    # ── episode maintenance ───────────────────────────────────────────────────

    async def fetch_episode_candidates(self, recency_days: int, max_batch: int) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, session_id, prompt, response, summary FROM memory_episodes"
                " WHERE created_at < NOW() - $1::interval"
                " AND summary IS NULL"
                " ORDER BY created_at ASC LIMIT $2",
                f"{recency_days} days",
                max_batch,
            )

    async def fetch_session_archive_candidates(
        self,
        recency_days: int,
        min_session_episodes: int,
        max_sessions: int,
    ) -> list:
        excluded_session_ids = ["", "app-main", "consolidator", "migrated"]
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT e.session_id, COUNT(*)::int AS n
                FROM memory_episodes e
                WHERE e.created_at < NOW() - $1::interval
                  AND e.summary IS NULL
                  AND e.session_id <> ALL($2::text[])
                  AND e.session_id NOT LIKE 'workflow:%'
                  AND e.session_id NOT LIKE 'onboarding:%'
                  AND e.session_id NOT LIKE 'eval-%'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM memory_episodes s
                    WHERE s.session_id = e.session_id
                      AND s.agent = 'consolidator'
                      AND s.summary IS NOT NULL
                  )
                GROUP BY e.session_id
                HAVING COUNT(*) >= $3
                ORDER BY MIN(e.created_at)
                LIMIT $4
                """,
                f"{recency_days} days",
                excluded_session_ids,
                min_session_episodes,
                max_sessions,
            )

    async def fetch_raw_session_episodes(self, session_id: str, recency_days: int) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                """
                SELECT id, prompt, response, created_at
                FROM memory_episodes
                WHERE session_id = $1
                  AND summary IS NULL
                  AND created_at < NOW() - $2::interval
                ORDER BY created_at ASC
                """,
                session_id,
                f"{recency_days} days",
            )

    async def replace_session_episodes_with_summary(
        self,
        session_id: str,
        episode_count: int,
        summary: str,
        embedding: Any,
        recency_days: int,
    ) -> int:
        emb_list = _to_list(embedding)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO memory_episodes"
                    " (session_id, agent, prompt, response, summary, embedding)"
                    " VALUES ($1, 'consolidator', $2, $3, $3, $4::vector)",
                    session_id,
                    f"{session_id}:{episode_count} episodes",
                    summary,
                    emb_list,
                )
                result = await conn.execute(
                    "DELETE FROM memory_episodes"
                    " WHERE session_id = $1"
                    " AND summary IS NULL"
                    " AND created_at < NOW() - $2::interval",
                    session_id,
                    f"{recency_days} days",
                )
        return _parse_update_count(result)

    async def insert_archive_episode(self, archive_text: str, session_id: str = "consolidator") -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO memory_episodes (session_id, agent, prompt, response, summary)"
                " VALUES ($1, 'consolidator', 'archive', $2, $2)",
                session_id,
                archive_text,
            )

    async def delete_episodes_by_ids(self, ids: list) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM memory_episodes WHERE id = ANY($1::uuid[])", ids
            )

    async def delete_old_episode_summaries(self, recency_days: int) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM memory_episodes"
                " WHERE summary IS NOT NULL"
                " AND created_at < NOW() - $1::interval",
                f"{recency_days * 2} days",
            )
        return _parse_update_count(result)

    # ── profile maintenance ───────────────────────────────────────────────────

    async def fetch_active_fact_summaries(self, limit: int) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT predicate, value FROM memory_facts WHERE contradicted = false"
                " ORDER BY updated_at DESC LIMIT $1",
                limit,
            )

    async def fetch_recent_episode_summaries(self, limit: int) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT summary FROM memory_episodes WHERE summary IS NOT NULL"
                " ORDER BY created_at DESC LIMIT $1",
                limit,
            )

    async def upsert_profile_facets(self, facets: list[dict]) -> None:
        async with self._pool.acquire() as conn:
            for facet in facets:
                await conn.execute(
                    """
                    INSERT INTO memory_profile_facets (key, value, stability, confidence, updated_at)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (key) DO UPDATE SET
                      value = EXCLUDED.value,
                      stability = EXCLUDED.stability,
                      confidence = EXCLUDED.confidence,
                      updated_at = NOW()
                    """,
                    facet["key"],
                    facet["value"],
                    facet.get("stability", "dynamic"),
                    facet.get("confidence", 0.8),
                )

    async def session_has_eager_summary(self, session_id: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT 1 FROM memory_session_summaries WHERE session_id = $1",
                session_id,
            )
        return row is not None

    async def delete_raw_session_episodes(self, session_id: str, recency_days: int) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memory_episodes
                WHERE session_id = $1
                  AND summary IS NULL
                  AND created_at < now() - ($2 || ' days')::interval
                """,
                session_id,
                str(recency_days),
            )
        deleted = int(result.split()[-1]) if result else 0
        return deleted
