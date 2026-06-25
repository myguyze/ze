from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_logging import get_logger
from ze_agents.nli import NLIClient
from ze_agents.types import RetrievalRequest
from ze_memory.nli_config import nli_config
from ze_memory.retrieval_cache import (
    PostgresRetrievalCacheStore,
    is_rerank_module,
    query_hash,
)

log = get_logger(__name__)

# Mirror policy LIMIT values in policies.py.
MODULE_RERANK_LIMITS: dict[str, dict[str, int]] = {
    "companion": {"facts": 50, "summaries": 10},
    "research": {"facts": 30, "summaries": 10},
    "email": {"facts": 20, "summaries": 10},
    "prospecting": {"facts": 30, "summaries": 10},
    "goals": {"facts": 30, "summaries": 0},
    "workflow": {"facts": 20, "summaries": 0},
    "calendar": {"facts": 20, "summaries": 0},
    "reminders": {"facts": 20, "summaries": 0},
}

_FACT_SELECT = """
    SELECT id, subject_id, predicate, object_text, object_id, value,
           confidence, reviewed, contradicted, source_episode_id, source_refs,
           COALESCE(provenance, 'raw') AS provenance
    FROM memory_facts
    WHERE contradicted = false
"""

_SUMMARY_SELECT = """
    SELECT id, session_id, summary, episode_count, last_turn_at,
           created_at, summary_updated_at
    FROM memory_session_summaries
    WHERE embedding IS NOT NULL
"""


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def nli_rank_score(score: dict[str, float] | None) -> float:
    if score is None:
        return 0.0
    return score["entailment"] + 0.5 * score["neutral"]


async def rerank_rows(
    rows: list[Any],
    text_field: str,
    query_text: str,
    *,
    min_candidates: int,
    nli_client: NLIClient | None = None,
) -> list[Any]:
    if len(rows) < min_candidates or nli_client is None:
        return list(rows)
    pairs = [(row[text_field], query_text) for row in rows]
    scores = await nli_client.scores(pairs)
    ranked: list[tuple[float, Any]] = []
    for row, score in zip(rows, scores):
        ranked.append((nli_rank_score(score), row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _, row in ranked]


async def rerank_row_ids(
    rows: list[Any],
    text_field: str,
    query_text: str,
    *,
    min_candidates: int,
    nli_client: NLIClient | None = None,
) -> list[UUID]:
    ordered = await rerank_rows(
        rows,
        text_field,
        query_text,
        min_candidates=min_candidates,
        nli_client=nli_client,
    )
    return [row["id"] for row in ordered]


async def fetch_fact_candidates(pool: Any, emb: str, limit: int) -> list[Any]:
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                f"""
                {_FACT_SELECT}
                ORDER BY
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $1::vector ELSE 1 END ASC,
                  updated_at DESC
                LIMIT $2
                """,
                emb,
                limit,
            )
        )


async def fetch_fact_candidates_by_cosine(pool: Any, emb: str, limit: int) -> list[Any]:
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                f"""
                {_FACT_SELECT}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                emb,
                limit,
            )
        )


async def fetch_summary_candidates(pool: Any, emb: str, limit: int) -> list[Any]:
    async with pool.acquire() as conn:
        return list(
            await conn.fetch(
                f"""
                {_SUMMARY_SELECT}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                emb,
                limit,
            )
        )


async def fetch_facts_by_ids(pool: Any, ids: list[UUID]) -> list[Any]:
    if not ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            {_FACT_SELECT}
            AND id = ANY($1::uuid[])
            """,
            ids,
        )
    by_id = {row["id"]: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


async def fetch_summaries_by_ids(pool: Any, ids: list[UUID]) -> list[Any]:
    if not ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            {_SUMMARY_SELECT}
            AND id = ANY($1::uuid[])
            """,
            ids,
        )
    by_id = {row["id"]: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def should_build_retrieval_cache(request: RetrievalRequest, cfg: dict[str, Any]) -> bool:
    if not cfg.get("nli_retrieval_rerank"):
        return False
    if not request.current_session_id or not request.query_text:
        return False
    if not is_rerank_module(request.module):
        return False
    return request.module in MODULE_RERANK_LIMITS


async def build_retrieval_cache(
    pool: Any,
    settings: Any,
    request: RetrievalRequest,
    *,
    nli_client: NLIClient | None = None,
) -> None:
    cfg = nli_config(settings)
    if not should_build_retrieval_cache(request, cfg) or nli_client is None:
        return

    limits = MODULE_RERANK_LIMITS[request.module]
    multiplier = int(cfg.get("nli_rerank_candidate_multiplier", 2))
    min_candidates = int(cfg.get("nli_rerank_min_candidates", 5))
    emb = _to_list(request.query_embedding)

    fact_limit = limits["facts"] * multiplier
    if request.module == "companion":
        fact_rows = await fetch_fact_candidates(pool, emb, fact_limit)
    else:
        fact_rows = await fetch_fact_candidates_by_cosine(pool, emb, fact_limit)

    fact_ids: list[UUID] = []
    if fact_rows:
        fact_ids = await rerank_row_ids(
            fact_rows,
            "value",
            request.query_text,
            min_candidates=min_candidates,
            nli_client=nli_client,
        )

    summary_ids: list[UUID] = []
    summary_limit = limits["summaries"]
    if summary_limit > 0:
        summary_rows = await fetch_summary_candidates(pool, emb, summary_limit * multiplier)
        if summary_rows:
            summary_ids = await rerank_row_ids(
                summary_rows,
                "summary",
                request.query_text,
                min_candidates=min_candidates,
                nli_client=nli_client,
            )

    session_id = request.current_session_id
    if session_id is None:
        return

    qhash = query_hash(request.module, request.query_text)
    cache = PostgresRetrievalCacheStore(pool)
    await cache.upsert(session_id, qhash, fact_ids, summary_ids)
    log.debug(
        "retrieval_cache_built",
        session_id=session_id,
        query_hash=qhash,
        fact_count=len(fact_ids),
        summary_count=len(summary_ids),
    )
