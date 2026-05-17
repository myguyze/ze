import asyncio
from uuid import UUID

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

from ze.logging import get_logger
from ze.memory.types import Episode, MemoryContext, UserFact
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings

_SUMMARY_SYSTEM = (
    "Summarise this AI assistant interaction in 1–2 sentences. Be concise and factual."
)

_DEFAULT_BUDGET = {"facts": 200, "episodes": 500}
_CONTRADICTION_THRESHOLD = 0.85


def _vec(embedding: np.ndarray) -> str:
    """Format a numpy vector for pgvector: '[v1,v2,...]'"""
    return "[" + ",".join(f"{x:.8f}" for x in embedding.tolist()) + "]"


def _tokens(text: str) -> int:
    return len(text) // 4


class MemoryStore:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._embedder = embedder
        self._client = openrouter_client
        self._settings = settings
        self._log = get_logger(__name__)

    # ── Public ────────────────────────────────────────────────────────────────

    async def get_context(
        self,
        prompt_embedding: np.ndarray,
        agent: str,
        token_budget: dict[str, int] | None = None,
    ) -> MemoryContext:
        budget = token_budget or _DEFAULT_BUDGET

        facts = await self._load_facts(agent, budget["facts"])
        episodes = await self._load_episodes(prompt_embedding, budget["episodes"])

        token_estimate = sum(_tokens(f.value) for f in facts)
        token_estimate += sum(_tokens(e.summary or e.response[:200]) for e in episodes)

        return MemoryContext(facts=facts, episodes=episodes, token_estimate=token_estimate)

    async def write_episode(
        self,
        agent: str,
        prompt: str,
        response: str,
        embedding: np.ndarray,
    ) -> None:
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO episodes (agent, prompt, response, embedding)
                    VALUES ($1, $2, $3, $4::vector)
                    """,
                    agent,
                    prompt,
                    response,
                    _vec(embedding),
                )
            self._log.debug("episode_written", agent=agent)
        except Exception as exc:
            self._log.warning("episode_write_failed", agent=agent, error=str(exc))

    async def propose_facts(self, proposals: list[UserFact]) -> None:
        if not proposals:
            return
        try:
            async with self._pool.acquire() as conn:
                for fact in proposals:
                    await self._write_fact_with_contradiction_check(conn, fact)
        except Exception as exc:
            self._log.warning("fact_propose_failed", error=str(exc))

    # ── Retrieval helpers ─────────────────────────────────────────────────────

    async def _load_facts(self, agent: str, token_budget: int) -> list[UserFact]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at
                FROM user_facts
                WHERE contradicted = false
                ORDER BY
                    CASE WHEN agent = $1 THEN 0 ELSE 1 END,
                    updated_at DESC
                """,
                agent,
            )

        facts: list[UserFact] = []
        used = 0
        for row in rows:
            cost = _tokens(row["value"])
            if used + cost > token_budget:
                break
            facts.append(UserFact(
                id=row["id"],
                key=row["key"],
                value=row["value"],
                agent=row["agent"],
                confidence=row["confidence"],
                reviewed=row["reviewed"],
                contradicted=row["contradicted"],
                updated_at=row["updated_at"],
            ))
            used += cost
        return facts

    async def _load_episodes(
        self,
        prompt_embedding: np.ndarray,
        token_budget: int,
    ) -> list[Episode]:
        vec_str = _vec(prompt_embedding)

        # Step 1: load candidates (release connection before network calls)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, agent, prompt, response, summary, created_at,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM episodes
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> $1::vector
                LIMIT 20
                """,
                vec_str,
            )

        if not rows:
            return []

        # Step 2: generate missing summaries concurrently (outside DB connection)
        missing = [r for r in rows if r["summary"] is None]
        generated: dict[UUID, str] = {}
        if missing:
            results = await asyncio.gather(
                *[self._generate_summary(r["id"], r["prompt"], r["response"]) for r in missing],
                return_exceptions=True,
            )
            for row, result in zip(missing, results):
                if isinstance(result, str):
                    generated[row["id"]] = result

        # Step 3: persist generated summaries in one connection
        if generated:
            async with self._pool.acquire() as conn:
                for episode_id, summary in generated.items():
                    await conn.execute(
                        "UPDATE episodes SET summary = $1 WHERE id = $2",
                        summary,
                        episode_id,
                    )

        # Step 4: build Episode objects within token budget
        episodes: list[Episode] = []
        used = 0
        for row in rows:
            summary = row["summary"] or generated.get(row["id"])
            text = summary or row["response"][:200]
            cost = _tokens(text)
            if used + cost > token_budget:
                break
            episodes.append(Episode(
                id=row["id"],
                agent=row["agent"],
                prompt=row["prompt"],
                response=row["response"],
                summary=summary,
                relevance=float(row["similarity"]),
                created_at=row["created_at"],
                # embedding intentionally left None — not needed for context injection
            ))
            used += cost
        return episodes

    async def _generate_summary(self, episode_id: UUID, prompt: str, response: str) -> str | None:
        model = self._settings.models_config.get("models", {}).get(
            "router", "anthropic/claude-haiku-4-5"
        )
        try:
            return await self._client.complete(
                messages=[{
                    "role": "user",
                    "content": f"Prompt: {prompt}\n\nResponse: {response[:1000]}",
                }],
                model=model,
                system=_SUMMARY_SYSTEM,
                max_tokens=100,
            )
        except Exception as exc:
            self._log.warning(
                "episode_summary_failed",
                episode_id=str(episode_id),
                error=str(exc),
            )
            return None

    # ── Write helpers ─────────────────────────────────────────────────────────

    async def _write_fact_with_contradiction_check(
        self, conn: asyncpg.Connection, fact: UserFact
    ) -> None:
        # Exact key match → mark existing as contradicted
        existing = await conn.fetchrow(
            "SELECT id FROM user_facts WHERE key = $1 AND contradicted = false",
            fact.key,
        )
        if existing:
            await conn.execute(
                "UPDATE user_facts SET contradicted = true WHERE id = $1",
                existing["id"],
            )
            self._log.info("fact_contradicted_exact_key", key=fact.key)

        # Embedding similarity → flag semantically contradictory entries
        value_embedding = self._embedder.encode(fact.value)
        all_rows = await conn.fetch(
            "SELECT id, key, value FROM user_facts WHERE key != $1 AND contradicted = false",
            fact.key,
        )
        threshold = float(
            self._settings.models_config.get("memory", {}).get(
                "contradiction_threshold", _CONTRADICTION_THRESHOLD
            )
        )
        for row in all_rows:
            other_embedding = self._embedder.encode(row["value"])
            similarity = float(np.dot(value_embedding, other_embedding))
            if similarity > threshold:
                await conn.execute(
                    "UPDATE user_facts SET contradicted = true WHERE id = $1",
                    row["id"],
                )
                self._log.info(
                    "fact_contradicted_semantic",
                    key=fact.key,
                    conflicting_key=row["key"],
                    similarity=round(similarity, 3),
                )

        # Insert the new fact (unreviewed by default)
        await conn.execute(
            """
            INSERT INTO user_facts (key, value, agent, confidence)
            VALUES ($1, $2, $3, $4)
            """,
            fact.key,
            fact.value,
            fact.agent,
            fact.confidence,
        )
        self._log.debug("fact_proposed", key=fact.key, agent=fact.agent)
