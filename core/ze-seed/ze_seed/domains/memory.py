from __future__ import annotations

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids, embedding_list
from ze_seed.narrative.ids import EPISODE_IDS, FACT_IDS, SEED_SESSION_ID


async def _clear_memory(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "memory_facts", FACT_IDS)
        await delete_by_ids(conn, "memory_episodes", EPISODE_IDS)
        await conn.execute(
            "DELETE FROM memory_profile_facets WHERE key LIKE 'seed-dev-%'"
        )


async def _apply_memory(ctx: SeedContext) -> int:
    if ctx.narrative is None:
        return 0
    count = 0
    async with ctx.pool.acquire() as conn:
        for ep in ctx.narrative.episodes:
            emb = embedding_list(ctx.embedder, ep.response)
            await conn.execute(
                """
                INSERT INTO memory_episodes
                    (id, session_id, agent, prompt, response, embedding)
                VALUES ($1, $2, $3, $4, $5, $6::vector)
                ON CONFLICT (id) DO NOTHING
                """,
                ep.id,
                SEED_SESSION_ID,
                ep.agent,
                ep.prompt,
                ep.response,
                emb,
            )
            count += 1

        for fact in ctx.narrative.facts:
            emb = embedding_list(ctx.embedder, fact.value)
            await conn.execute(
                """
                INSERT INTO memory_facts
                    (id, predicate, value, confidence, reviewed, contradicted,
                     source_episode_id, source_refs, embedding, agent)
                VALUES ($1, $2, $3, $4, true, false, $5, '[]'::jsonb, $6::vector, $7)
                ON CONFLICT (id) DO NOTHING
                """,
                fact.id,
                fact.predicate,
                fact.value,
                fact.confidence,
                fact.source_episode_id,
                emb,
                fact.agent,
            )
            count += 1

        await conn.execute(
            """
            INSERT INTO memory_profile_facets (key, value, confidence)
            VALUES ($1, $2, 1.0)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            "seed-dev-communication_style",
            ctx.narrative.communication_style,
        )
        count += 1

    return count


def memory_seed_domains() -> list[SeedDomain]:
    return [
        SeedDomain("memory.dev", seed_order=15, clear=_clear_memory, apply=_apply_memory),
    ]
