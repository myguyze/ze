from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from ze_core.logging import get_logger

from ze_memory.defaults import (
    CONTRADICTION_THRESHOLD,
    DEFAULT_EPISODE_BUDGET_TOKENS,
    DEFAULT_FACT_BUDGET_TOKENS,
    EPISODES_FETCH_LIMIT,
    MODEL_SYNTHESIS,
)
from ze_memory.errors import InvalidRetrievalRequestError, StoreError
from ze_memory.policies import DefaultPolicyRegistry
from ze_memory.projection import (
    budget_episodes,
    budget_facts,
    facets_from_rows,
    task_state_from_row,
    token_estimate,
)
from ze_memory.types import (
    Fact,
    MemoryContext,
    ProfileFacet,
    RetrievalRequest,
    TaskState,
)

log = get_logger(__name__)


def _to_list(embedding: Any) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _cosine_similarity(a: Any, b: Any) -> float:
    if hasattr(a, "dot"):
        dot = float(a.dot(b))
        norm_a = float((a * a).sum() ** 0.5)
        norm_b = float((b * b).sum() ** 0.5)
    else:
        a_l = list(a)
        b_l = list(b)
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


class PostgresMemoryStore:
    def __init__(
        self,
        pool: Any,
        embedder: Any,
        openrouter_client: Any,
        settings: Any = None,
        policy_registry: Any = None,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._registry = policy_registry or DefaultPolicyRegistry()

    # ── MemoryStore protocol ──────────────────────────────────────────────────

    async def retrieve(self, request: RetrievalRequest) -> MemoryContext:
        if not request.module:
            raise InvalidRetrievalRequestError("RetrievalRequest.module is required")
        if request.query_embedding is None:
            raise InvalidRetrievalRequestError("RetrievalRequest.query_embedding is required")

        policy = self._registry.for_module(request.module)
        return await policy.retrieve(request, self)

    async def write_episode(
        self,
        session_id: str,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None:
        try:
            emb_list = _to_list(embedding)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO memory_episodes"
                    " (session_id, agent, prompt, response, embedding)"
                    " VALUES ($1, $2, $3, $4, $5::vector)",
                    session_id,
                    agent,
                    prompt,
                    response,
                    emb_list,
                )
        except Exception as exc:
            log.warning("memory_write_episode_failed", error=str(exc))

    async def propose_facts(self, proposals: list[Fact]) -> None:
        for fact in proposals:
            try:
                await self._write_fact_with_contradiction_check(fact)
            except Exception as exc:
                log.warning(
                    "memory_propose_fact_failed",
                    predicate=fact.predicate,
                    error=str(exc),
                )

    async def upsert_task_state(self, state: TaskState) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_task_state
                  (task_id, goal_id, status, open_steps, blocked_by,
                   last_action, next_action, tool_cursors, updated_at)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8::jsonb, NOW())
                ON CONFLICT (task_id) WHERE task_id IS NOT NULL DO UPDATE SET
                  status = EXCLUDED.status,
                  open_steps = EXCLUDED.open_steps,
                  blocked_by = EXCLUDED.blocked_by,
                  last_action = EXCLUDED.last_action,
                  next_action = EXCLUDED.next_action,
                  tool_cursors = EXCLUDED.tool_cursors,
                  updated_at = NOW()
                """,
                state.task_id,
                state.goal_id,
                state.status,
                json.dumps(state.open_steps),
                json.dumps(state.blocked_by),
                state.last_action,
                state.next_action,
                json.dumps(state.tool_cursors),
            )

    async def get_task_state(
        self,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> TaskState | None:
        if task_id is None and goal_id is None:
            return None
        async with self._pool.acquire() as conn:
            if task_id is not None:
                row = await conn.fetchrow(
                    "SELECT * FROM memory_task_state WHERE task_id = $1", task_id
                )
            else:
                row = await conn.fetchrow(
                    "SELECT * FROM memory_task_state WHERE goal_id = $1"
                    " ORDER BY updated_at DESC LIMIT 1",
                    goal_id,
                )
        if row is None:
            return None
        return task_state_from_row(row)

    async def get_profile(self) -> list[ProfileFacet]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT key, value, stability, confidence, source_refs, updated_at"
                " FROM memory_profile_facets ORDER BY confidence DESC"
            )
        return facets_from_rows(rows, budget_tokens=10_000)

    # ── convenience methods for jobs/introspection ────────────────────────────

    async def list_recent_facts(self, days: int, limit: int) -> list[Fact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE contradicted = false
                  AND updated_at >= now() - ($1 || ' days')::interval
                ORDER BY confidence DESC, updated_at DESC
                LIMIT $2
                """,
                str(days),
                limit,
            )
        return budget_facts(rows, DEFAULT_FACT_BUDGET_TOKENS * 20)

    async def list_recent_episodes(self, days: int, limit: int) -> list[Any]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, agent, prompt, response, summary,
                       relevance, created_at, linked_entity_ids, linked_fact_ids
                FROM memory_episodes
                WHERE created_at >= now() - ($1 || ' days')::interval
                ORDER BY created_at DESC
                LIMIT $2
                """,
                str(days),
                limit,
            )
        return budget_episodes(rows, DEFAULT_EPISODE_BUDGET_TOKENS * 20)

    # ── internal ──────────────────────────────────────────────────────────────

    async def _write_fact_with_contradiction_check(self, fact: Fact) -> None:
        threshold = self._memory_config().get("contradiction_threshold", CONTRADICTION_THRESHOLD)
        value_emb = self._embedder.encode(fact.value)
        emb_list = _to_list(value_emb)

        async with self._pool.acquire() as conn:
            exact = await conn.fetch(
                "SELECT id FROM memory_facts WHERE predicate = $1 AND contradicted = false",
                fact.predicate,
            )
            for row in exact:
                await conn.execute(
                    "UPDATE memory_facts SET contradicted = true WHERE id = $1",
                    row["id"],
                )

            others = await conn.fetch(
                "SELECT id, value FROM memory_facts WHERE contradicted = false AND predicate != $1",
                fact.predicate,
            )
            for row in others:
                other_emb = self._embedder.encode(row["value"])
                if _cosine_similarity(value_emb, other_emb) > threshold:
                    await conn.execute(
                        "UPDATE memory_facts SET contradicted = true WHERE id = $1",
                        row["id"],
                    )

            await conn.execute(
                "INSERT INTO memory_facts"
                " (subject_id, predicate, object_text, object_id, value,"
                "  confidence, reviewed, contradicted,"
                "  source_episode_id, source_refs, embedding)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::vector)",
                fact.subject_id,
                fact.predicate,
                fact.object_text,
                fact.object_id,
                fact.value,
                fact.confidence,
                fact.reviewed,
                fact.contradicted,
                fact.source_episode_id,
                json.dumps([str(r) for r in fact.source_refs]),
                emb_list,
            )

    async def _generate_summary(self, episode_id: Any, prompt: str, response: str) -> str | None:
        try:
            return await self._client.complete(
                messages=[{
                    "role": "user",
                    "content": (
                        "Summarize this interaction in one sentence.\n"
                        f"User: {prompt}\nAssistant: {response}"
                    ),
                }],
                model=self._synthesis_model(),
                max_tokens=100,
            )
        except Exception as exc:
            log.warning(
                "memory_summary_generation_failed",
                episode_id=str(episode_id),
                error=str(exc),
            )
            return None

    # ── consolidation support methods ─────────────────────────────────────────

    async def fetch_active_facts(self) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, predicate, value, confidence"
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
                "INSERT INTO memory_facts (predicate, value, confidence, embedding)"
                " VALUES ($1, $2, $3, $4::vector)",
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

    async def fetch_episode_candidates(self, recency_days: int, max_batch: int) -> list:
        async with self._pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, session_id, prompt, response, summary FROM memory_episodes"
                " WHERE created_at < NOW() - $1::interval"
                " ORDER BY created_at ASC LIMIT $2",
                f"{recency_days} days",
                max_batch,
            )

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

    def _memory_config(self) -> dict:
        if self._settings is None:
            return {}
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("memory", {})
        if isinstance(self._settings, dict):
            return self._settings.get("memory", {})
        return {}

    def _synthesis_model(self) -> str:
        if self._settings is None:
            return MODEL_SYNTHESIS
        cfg = getattr(self._settings, "config", None)
        if isinstance(cfg, dict):
            return cfg.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        if isinstance(self._settings, dict):
            return self._settings.get("models", {}).get("synthesis", MODEL_SYNTHESIS)
        return MODEL_SYNTHESIS
