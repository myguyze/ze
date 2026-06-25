from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID

from ze_memory.types import RetrievalCacheEntry

_EXCLUDED_MODULES = frozenset({"profile", "memory_ui", "planner", "tool_executor"})


def query_hash(module: str, query_text: str) -> str:
    normalized = f"{module}:{query_text.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def is_rerank_module(module: str) -> bool:
    return module not in _EXCLUDED_MODULES


class PostgresRetrievalCacheStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def get(self, session_id: str, qhash: str) -> RetrievalCacheEntry | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT session_id, query_hash, fact_ranked_ids, summary_ranked_ids, created_at
                FROM memory_retrieval_cache
                WHERE session_id = $1 AND query_hash = $2
                """,
                session_id,
                qhash,
            )
        if row is None:
            return None
        return RetrievalCacheEntry(
            session_id=row["session_id"],
            query_hash=row["query_hash"],
            fact_ranked_ids=list(row["fact_ranked_ids"] or []),
            summary_ranked_ids=list(row["summary_ranked_ids"] or []),
            created_at=row["created_at"],
        )

    async def upsert(
        self,
        session_id: str,
        qhash: str,
        fact_ids: list[UUID],
        summary_ids: list[UUID],
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_retrieval_cache (
                    session_id, query_hash, fact_ranked_ids, summary_ranked_ids, created_at
                )
                VALUES ($1, $2, $3::uuid[], $4::uuid[], now())
                ON CONFLICT (session_id, query_hash) DO UPDATE SET
                    fact_ranked_ids = EXCLUDED.fact_ranked_ids,
                    summary_ranked_ids = EXCLUDED.summary_ranked_ids,
                    created_at = now()
                """,
                session_id,
                qhash,
                fact_ids,
                summary_ids,
            )

    async def expire_older_than(self, days: int = 1) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM memory_retrieval_cache
                WHERE created_at < now() - ($1::text || ' days')::interval
                """,
                str(days),
            )
        return int(result.split()[-1]) if result else 0


async def expire_retrieval_cache(pool: Any, *, days: int = 1) -> int:
    store = PostgresRetrievalCacheStore(pool)
    return await store.expire_older_than(days=days)
