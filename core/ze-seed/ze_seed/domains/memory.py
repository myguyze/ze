from __future__ import annotations

import json

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.domains._helpers import delete_by_ids, embedding_vector
from ze_seed.narrative.ids import (
    ENTITY_IDS,
    EPISODE_IDS,
    FACT_IDS,
    RELATIONSHIP_IDS,
    SEED_SESSION_ID,
)


async def _clear_memory(ctx: SeedContext) -> None:
    async with ctx.pool.acquire() as conn:
        await delete_by_ids(conn, "memory_facts", FACT_IDS)
        await delete_by_ids(conn, "memory_relationships", RELATIONSHIP_IDS)
        await delete_by_ids(conn, "memory_entities", ENTITY_IDS)
        await delete_by_ids(conn, "memory_episodes", EPISODE_IDS)
        await conn.execute(
            "DELETE FROM memory_profile_facets WHERE key LIKE 'seed-dev-%'"
        )


async def _apply_memory(ctx: SeedContext) -> int:
    if ctx.narrative is None:
        return 0
    count = 0
    async with ctx.pool.acquire() as conn:
        for entity in ctx.narrative.entities:
            emb = embedding_vector(ctx.embedder, entity.canonical_name)
            await conn.execute(
                """
                INSERT INTO memory_entities
                    (id, entity_type, canonical_name, aliases, attrs, embedding)
                VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6::vector)
                ON CONFLICT (id) DO NOTHING
                """,
                entity.id,
                entity.entity_type,
                entity.canonical_name,
                json.dumps(entity.aliases),
                json.dumps(entity.attrs),
                emb,
            )
            count += 1

        for rel in ctx.narrative.relationships:
            await conn.execute(
                """
                INSERT INTO memory_relationships
                    (id, source_id, source_type, predicate,
                     target_id, target_type, confidence,
                     creation_method, reviewed)
                VALUES ($1, $2, 'entity', $3, $4, 'entity', $5, 'explicit', true)
                ON CONFLICT (id) DO NOTHING
                """,
                rel.id,
                rel.source_id,
                rel.predicate,
                rel.target_id,
                rel.confidence,
            )
            count += 1

        for ep in ctx.narrative.episodes:
            emb = embedding_vector(ctx.embedder, ep.response)
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
            emb = embedding_vector(ctx.embedder, fact.value)
            await conn.execute(
                """
                INSERT INTO memory_facts
                    (id, subject_id, object_id, predicate, value, confidence,
                     reviewed, contradicted, source_episode_id, source_refs,
                     embedding, agent)
                VALUES ($1, $2, $3, $4, $5, $6, true, false, $7,
                        '[]'::jsonb, $8::vector, $9)
                ON CONFLICT (id) DO NOTHING
                """,
                fact.id,
                fact.subject_id,
                fact.object_id,
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
