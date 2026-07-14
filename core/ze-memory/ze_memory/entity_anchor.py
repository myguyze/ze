"""Entity-anchored retrieval — matches known entities in query text and pulls

their one-hop graph neighbourhood as a second, non-vector retrieval entry point
(User Story 2, phase 106). This complements (does not replace) the existing
post-hoc `_graph_augment` decoration path in `retriever.py`, which seeds
expansion from already-retrieved candidates rather than the query text itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from ze_logging import get_logger
from ze_memory.dream.retrieval import episode_retrievable_sql
from ze_memory.graph.store import GraphStore
from ze_memory.projection import _episode_from_row, _fact_from_row, _load_json
from ze_memory.relevance_config import RelevanceConfig
from ze_memory.types import Entity, MemoryContext

log = get_logger(__name__)

_FACT_SELECT = """
    SELECT id, subject_id, predicate, object_text, object_id, value,
           confidence, reviewed, contradicted, source_episode_id, source_refs,
           COALESCE(provenance, 'raw') AS provenance
    FROM memory_facts
"""


@dataclass
class EntityAnchorMatch:
    entity: Entity
    matched_text: str  # the substring of the query that matched (name or alias)
    match_kind: Literal["canonical_name", "alias"]


def _word_bounded_match(name: str, text: str) -> bool:
    name = name.strip()
    if not name:
        return False
    pattern = r"\b" + re.escape(name) + r"\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


async def match_entities_in_query(query_text: str, pool: Any) -> list[EntityAnchorMatch]:
    """Word-bounded, case-insensitive match of known entities against query text.

    Canonical-name matches take precedence over alias matches for the same
    entity (spec Edge Cases: "prefer the canonical name over alias collisions").
    Returns [] (never raises) on any DB error — entity-anchor retrieval degrades
    to vector-only silently.
    """
    if not query_text or not query_text.strip():
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, entity_type, canonical_name, aliases, attrs"
                " FROM memory_entities"
            )
    except Exception as exc:
        log.warning("entity_anchor_match_query_failed", error=str(exc))
        return []

    matches: dict[UUID, EntityAnchorMatch] = {}
    for row in rows:
        entity_id = row["id"]
        canonical_name = row["canonical_name"] or ""
        if _word_bounded_match(canonical_name, query_text):
            matches[entity_id] = EntityAnchorMatch(
                entity=Entity(
                    id=entity_id,
                    entity_type=row["entity_type"],
                    canonical_name=canonical_name,
                    aliases=_load_json(row["aliases"]),
                    attrs=_load_json(row["attrs"]),
                ),
                matched_text=canonical_name,
                match_kind="canonical_name",
            )
            continue

        for alias in _load_json(row["aliases"]):
            if alias and _word_bounded_match(alias, query_text):
                matches[entity_id] = EntityAnchorMatch(
                    entity=Entity(
                        id=entity_id,
                        entity_type=row["entity_type"],
                        canonical_name=canonical_name,
                        aliases=_load_json(row["aliases"]),
                        attrs=_load_json(row["attrs"]),
                    ),
                    matched_text=alias,
                    match_kind="alias",
                )
                break

    return list(matches.values())


async def fetch_anchored_candidates(
    matches: list[EntityAnchorMatch],
    graph_store: GraphStore,
    pool: Any,
    cfg: RelevanceConfig,
    *,
    current_session_id: str | None = None,
) -> MemoryContext:
    """One-hop DESCRIBES/SOURCED_FROM neighbours of matched entities.

    Every candidate gets `relevance_score = cfg.entity_match_constant` (the
    vector-similarity term of FR-009's max() rule is applied later, in
    `merge_candidates`, once the vector-path score for the same ID is known)
    and `retrieval_provenance = "entity_anchor"`. Applies the same validity
    filters as vector candidates: `contradicted = false`, `episode_retrievable_sql()`,
    current-session exclusion.
    """
    if not matches:
        return MemoryContext()

    seed_ids = [m.entity.id for m in matches if m.entity.id is not None]
    if not seed_ids:
        return MemoryContext()

    try:
        expansion = await graph_store.expand(seed_ids, max_hops=1)
    except Exception as exc:
        log.warning("entity_anchor_expand_failed", error=str(exc))
        return MemoryContext()

    if expansion.is_empty():
        return MemoryContext()

    facts = []
    episodes = []

    try:
        async with pool.acquire() as conn:
            if expansion.fact_ids:
                rows = await conn.fetch(
                    f"""
                    {_FACT_SELECT}
                    WHERE id = ANY($1::uuid[]) AND contradicted = false
                    """,
                    expansion.fact_ids,
                )
                for row in rows:
                    fact = _fact_from_row(row)
                    fact.relevance_score = cfg.entity_match_constant
                    fact.retrieval_provenance = "entity_anchor"
                    facts.append(fact)

            if expansion.episode_ids:
                rows = await conn.fetch(
                    f"""
                    SELECT id, session_id, agent, prompt, response, summary,
                           relevance, created_at, linked_entity_ids, linked_fact_ids
                    FROM memory_episodes
                    WHERE id = ANY($1::uuid[])
                      AND ($2::text IS NULL OR session_id IS DISTINCT FROM $2)
                      {episode_retrievable_sql()}
                    """,
                    expansion.episode_ids,
                    current_session_id,
                )
                for row in rows:
                    episode = _episode_from_row(row)
                    episode.relevance_score = cfg.entity_match_constant
                    episode.retrieval_provenance = "entity_anchor"
                    episodes.append(episode)
    except Exception as exc:
        log.warning("entity_anchor_fetch_failed", error=str(exc))
        return MemoryContext()

    return MemoryContext(facts=facts, episodes=episodes)


def _merge_list(vector_items: list, anchor_items: list) -> list:
    """Dedup by id, keeping the item whose relevance_score is highest (FR-008/FR-009)."""
    by_id: dict[Any, Any] = {}
    ordered_ids: list = []
    passthrough: list = []

    for item in vector_items:
        key = getattr(item, "id", None)
        if key is None:
            passthrough.append(item)
            continue
        if getattr(item, "retrieval_provenance", None) is None:
            item.retrieval_provenance = "vector"
        by_id[key] = item
        ordered_ids.append(key)

    for item in anchor_items:
        key = getattr(item, "id", None)
        if key is None:
            passthrough.append(item)
            continue
        existing = by_id.get(key)
        if existing is None:
            by_id[key] = item
            ordered_ids.append(key)
            continue
        existing_score = existing.relevance_score or 0.0
        candidate_score = item.relevance_score or 0.0
        if candidate_score > existing_score:
            by_id[key] = item
        else:
            by_id[key].relevance_score = max(existing_score, candidate_score)

    seen: set = set()
    result = []
    for key in ordered_ids:
        if key in seen:
            continue
        seen.add(key)
        result.append(by_id[key])
    result.extend(passthrough)
    return result


def merge_candidates(vector_ctx: MemoryContext, anchor_ctx: MemoryContext) -> MemoryContext:
    """Merge entity-anchored candidates into a vector-retrieved MemoryContext.

    Dedups facts/episodes/entities/events by ID, keeping the strongest evidence
    (max relevance_score) per FR-008/FR-009. Everything else on vector_ctx
    (session_summaries, procedures, task_state, profile) passes through unchanged.
    """
    from ze_memory.projection import token_estimate

    merged = MemoryContext(
        facts=_merge_list(vector_ctx.facts, anchor_ctx.facts),
        episodes=_merge_list(vector_ctx.episodes, anchor_ctx.episodes),
        session_summaries=vector_ctx.session_summaries,
        events=_merge_list(vector_ctx.events, anchor_ctx.events),
        procedures=vector_ctx.procedures,
        task_state=vector_ctx.task_state,
        profile=vector_ctx.profile,
        entities=_merge_list(vector_ctx.entities, anchor_ctx.entities),
    )
    merged.token_estimate = token_estimate(merged)
    return merged


async def augment_with_entity_anchor(
    ctx: MemoryContext,
    query_text: str,
    pool: Any,
    graph_store: GraphStore | None,
    cfg: RelevanceConfig,
    *,
    current_session_id: str | None = None,
) -> MemoryContext:
    """Entry point policies call after their own vector fetch+floor+budget.

    Gated by `cfg.entity_anchor_enabled`; degrades to vector-only (returns ctx
    unchanged) on any failure or when disabled/no graph store, matching the
    `_graph_augment` graceful-degradation pattern in `retriever.py`.
    """
    if not cfg.entity_anchor_enabled or graph_store is None:
        return ctx
    try:
        matches = await match_entities_in_query(query_text, pool)
        if not matches:
            return ctx
        anchor_ctx = await fetch_anchored_candidates(
            matches,
            graph_store,
            pool,
            cfg,
            current_session_id=current_session_id,
        )
        return merge_candidates(ctx, anchor_ctx)
    except Exception as exc:
        log.warning("entity_anchor_augment_failed", error=str(exc))
        return ctx
