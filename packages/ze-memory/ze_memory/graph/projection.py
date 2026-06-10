"""Enrich a MemoryContext with data discovered via graph expansion."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_memory.defaults import DEFAULT_FACT_BUDGET_TOKENS
from ze_memory.graph.types import GraphExpansion
from ze_memory.projection import (
    budget_facts,
    entities_from_rows,
    token_estimate,
)
from ze_memory.types import Entity, Fact, MemoryContext


async def enrich_context(
    ctx: MemoryContext,
    expansion: GraphExpansion,
    pool: Any,
    token_budget: int = 500,
) -> MemoryContext:
    """Fetch facts and entities discovered by graph expansion and merge into ctx.

    Only IDs not already present in ctx are fetched. Token budget limits how much
    graph-discovered content is added. Returns a new MemoryContext (ctx is unchanged).
    """
    if expansion.is_empty():
        return ctx

    existing_fact_ids: set[UUID] = {f.id for f in ctx.facts if f.id is not None}
    existing_entity_ids: set[UUID] = {e.id for e in ctx.entities if e.id is not None}

    new_fact_ids = [fid for fid in expansion.fact_ids if fid not in existing_fact_ids]
    new_entity_ids = [eid for eid in expansion.entity_ids if eid not in existing_entity_ids]

    extra_facts: list[Fact] = []
    extra_entities: list[Entity] = []

    async with pool.acquire() as conn:
        if new_fact_ids:
            rows = await conn.fetch(
                """
                SELECT id, subject_id, predicate, object_text, object_id, value,
                       confidence, reviewed, contradicted, source_episode_id, source_refs
                FROM memory_facts
                WHERE id = ANY($1) AND contradicted = false
                ORDER BY confidence DESC
                """,
                new_fact_ids,
            )
            extra_facts = budget_facts(rows, token_budget)

        if new_entity_ids:
            rows = await conn.fetch(
                "SELECT id, entity_type, canonical_name, aliases, attrs"
                " FROM memory_entities WHERE id = ANY($1)",
                new_entity_ids,
            )
            extra_entities = entities_from_rows(rows)

    if not extra_facts and not extra_entities:
        return ctx

    merged = MemoryContext(
        facts=ctx.facts + extra_facts,
        episodes=ctx.episodes,
        events=ctx.events,
        procedures=ctx.procedures,
        task_state=ctx.task_state,
        profile=ctx.profile,
        entities=ctx.entities + extra_entities,
    )
    merged.token_estimate = token_estimate(merged)
    return merged
