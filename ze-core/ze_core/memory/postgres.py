from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from ze_core.defaults import (
    MEMORY_CONTRADICTION_THRESHOLD,
    MEMORY_EPISODES_FETCH_LIMIT,
    MEMORY_EPISODES_TOKEN_BUDGET,
    MEMORY_FACTS_TOKEN_BUDGET,
    MODEL_SYNTHESIS,
)
from ze_core.logging import get_logger
from ze_core.memory.types import Episode, MemoryContext, UserFact, UserProfile

log = get_logger(__name__)

_DEFAULT_BUDGET = {"facts": MEMORY_FACTS_TOKEN_BUDGET, "episodes": MEMORY_EPISODES_TOKEN_BUDGET}


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


def _to_list(embedding: Any) -> list:
    return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)


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
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings

    # ── public API ────────────────────────────────────────────────────────────

    async def get_context(
        self,
        prompt_embedding: Any,
        agent: str,
        token_budget: dict[str, int] | None = None,
    ) -> MemoryContext:
        budget = {**_DEFAULT_BUDGET, **(token_budget or {})}
        emb_list = _to_list(prompt_embedding)

        async with self._pool.acquire() as conn:
            facts_rows = await conn.fetch(
                """
                SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at
                FROM user_facts
                WHERE contradicted = false
                  AND (agent = $1 OR agent = 'global')
                ORDER BY
                  CASE WHEN agent = $1 THEN 0 ELSE 1 END,
                  CASE WHEN embedding IS NOT NULL
                       THEN embedding <=> $2::vector ELSE 1 END ASC,
                  updated_at DESC
                """,
                agent,
                emb_list,
            )
            episode_rows = await conn.fetch(
                """
                SELECT id, agent, prompt, response, summary, is_archive, created_at
                FROM episodes
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                emb_list,
                MEMORY_EPISODES_FETCH_LIMIT,
            )
            profile_row = await conn.fetchrow(
                "SELECT preferences, habits, topics, relationships, goals, updated_at, version"
                " FROM user_profile WHERE id = 1"
            )

        facts = _apply_budget(facts_rows, budget["facts"], _fact_from_row)
        episodes, missing = _collect_episodes(episode_rows, budget["episodes"])

        if missing:
            await self._fill_summaries(episodes, missing)

        profile = _profile_from_row(profile_row)
        token_est = sum(len(f.value) // 4 for f in facts) + sum(
            len(e.summary or e.response[:200]) // 4 for e in episodes
        )
        return MemoryContext(
            facts=facts,
            episodes=episodes,
            token_estimate=token_est,
            profile=profile,
        )

    async def write_episode(
        self,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None:
        try:
            emb_list = _to_list(embedding)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO episodes (agent, prompt, response, embedding)"
                    " VALUES ($1, $2, $3, $4::vector)",
                    agent,
                    prompt,
                    response,
                    emb_list,
                )
        except Exception as exc:
            log.warning("memory_write_episode_failed", error=str(exc))

    async def propose_facts(self, proposals: list[UserFact]) -> None:
        for fact in proposals:
            try:
                await self._write_fact_with_contradiction_check(fact)
            except Exception as exc:
                log.warning("memory_propose_fact_failed", key=fact.key, error=str(exc))

    async def get_profile(self) -> UserProfile | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT preferences, habits, topics, relationships, goals, updated_at, version"
                " FROM user_profile WHERE id = 1"
            )
        return _profile_from_row(row)

    # ── internal ──────────────────────────────────────────────────────────────

    async def _write_fact_with_contradiction_check(self, fact: UserFact) -> None:
        threshold = self._memory_config().get(
            "contradiction_threshold", MEMORY_CONTRADICTION_THRESHOLD
        )
        value_emb = self._embedder.encode(fact.value)
        emb_list = _to_list(value_emb)

        async with self._pool.acquire() as conn:
            exact = await conn.fetch(
                "SELECT id FROM user_facts WHERE key = $1 AND contradicted = false",
                fact.key,
            )
            for row in exact:
                await conn.execute(
                    "UPDATE user_facts SET contradicted = true WHERE id = $1",
                    row["id"],
                )

            others = await conn.fetch(
                "SELECT id, value FROM user_facts WHERE contradicted = false AND key != $1",
                fact.key,
            )
            for row in others:
                other_emb = self._embedder.encode(row["value"])
                if _cosine_similarity(value_emb, other_emb) > threshold:
                    await conn.execute(
                        "UPDATE user_facts SET contradicted = true WHERE id = $1",
                        row["id"],
                    )

            await conn.execute(
                "INSERT INTO user_facts"
                " (key, value, agent, confidence, reviewed, contradicted, embedding)"
                " VALUES ($1, $2, $3, $4, $5, $6, $7::vector)",
                fact.key,
                fact.value,
                fact.agent,
                fact.confidence,
                fact.reviewed,
                fact.contradicted,
                emb_list,
            )

    async def _generate_summary(
        self, episode_id: UUID, prompt: str, response: str
    ) -> str | None:
        model = self._synthesis_model()
        try:
            return await self._client.complete(
                messages=[
                    {
                        "role": "user",
                        "content": (
                            "Summarize this interaction in one sentence.\n"
                            f"User: {prompt}\nAssistant: {response}"
                        ),
                    }
                ],
                model=model,
                max_tokens=100,
            )
        except Exception as exc:
            log.warning(
                "memory_summary_generation_failed",
                episode_id=str(episode_id),
                error=str(exc),
            )
            return None

    async def _fill_summaries(
        self,
        episodes: list[Episode],
        missing: list[tuple[Episode, UUID, str, str]],
    ) -> None:
        summaries = await asyncio.gather(
            *[self._generate_summary(ep_id, p, r) for _, ep_id, p, r in missing],
            return_exceptions=True,
        )
        async with self._pool.acquire() as conn:
            for (ep, ep_id, _, _), summary in zip(missing, summaries):
                if isinstance(summary, str):
                    ep.summary = summary
                    await conn.execute(
                        "UPDATE episodes SET summary = $1 WHERE id = $2",
                        summary,
                        ep_id,
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


# ── helpers ───────────────────────────────────────────────────────────────────

def _fact_from_row(row: Any) -> UserFact:
    return UserFact(
        key=row["key"],
        value=row["value"],
        agent=row["agent"],
        confidence=row["confidence"],
        reviewed=row["reviewed"],
        contradicted=row["contradicted"],
        id=row["id"],
        updated_at=row["updated_at"],
    )


def _apply_budget(rows: list, budget: int, factory: Any) -> list:
    items = []
    used = 0
    for row in rows:
        text = row.get("value") or row.get("response") or ""
        cost = len(text) // 4
        if used + cost > budget:
            break
        items.append(factory(row))
        used += cost
    return items


def _collect_episodes(
    rows: list, budget: int
) -> tuple[list[Episode], list[tuple[Episode, Any, str, str]]]:
    episodes: list[Episode] = []
    missing: list[tuple[Episode, Any, str, str]] = []
    used = 0
    for row in rows:
        text = row["summary"] or row["response"][:200]
        cost = len(text) // 4
        if used + cost > budget:
            break
        ep = Episode(
            agent=row["agent"],
            prompt=row["prompt"],
            response=row["response"],
            summary=row["summary"],
            is_archive=row["is_archive"],
            id=row["id"],
            created_at=row["created_at"],
        )
        episodes.append(ep)
        used += cost
        if row["summary"] is None:
            missing.append((ep, row["id"], row["prompt"], row["response"]))
    return episodes, missing


def _profile_from_row(row: Any) -> UserProfile | None:
    if row is None:
        return None
    prefs, habits, topics, rels, goals = (
        row["preferences"],
        row["habits"],
        row["topics"],
        row["relationships"],
        row["goals"],
    )
    if not any([prefs, habits, topics, rels, goals]):
        return None
    return UserProfile(
        preferences=prefs,
        habits=habits,
        topics=topics,
        relationships=rels,
        goals=goals,
        updated_at=row["updated_at"],
        version=row["version"],
    )
