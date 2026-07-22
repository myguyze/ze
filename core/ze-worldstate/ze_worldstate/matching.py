from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_logging import get_logger
from ze_memory.consolidation_store import _cosine_similarity
from ze_memory.graph.store import GraphStore

from ze_worldstate.store import LoopStore
from ze_worldstate.types import OpenLoop

log = get_logger(__name__)

# Plan-time tunable (not spec-mandated) — cosine similarity floor for the
# embedding tiebreaker to consider two loop titles "the same loop" (research.md §5).
DEFAULT_SIMILARITY_THRESHOLD = 0.75


async def _loops_linked_to_entities(
    entity_ids: list[UUID],
    graph_store: GraphStore,
    loop_store: LoopStore,
) -> list[OpenLoop]:
    if not entity_ids:
        return []
    relationships = await graph_store.list_relationships(
        entity_ids, predicates=["has_open_loop"]
    )
    loop_ids = {
        rel.target_id
        for rel in relationships
        if rel.target_type == "open_loop" and rel.target_id is not None
    }
    loops = []
    for loop_id in loop_ids:
        loop = await loop_store.get(loop_id)
        if loop is not None:
            loops.append(loop)
    return loops


async def find_matching_loop(
    entity_ids: list[UUID],
    candidate_title: str,
    *,
    loop_store: LoopStore,
    graph_store: GraphStore,
    embedder: Any,
    states: list[str] | None = None,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> OpenLoop | None:
    """Entity-overlap primary, embedding-similarity-on-title tiebreaker (research.md §5).

    Reused for both FR-010 (attach/strengthen an existing loop instead of
    duplicating) and FR-011 (recognise dismissed-then-re-implied evidence
    against `dropped` loops — pass states=["dropped"]).
    """
    candidates = await _loops_linked_to_entities(entity_ids, graph_store, loop_store)
    if states is not None:
        candidates = [c for c in candidates if c.state.value in states]

    if len(candidates) == 1:
        return candidates[0]

    if len(candidates) > 1:
        pool = candidates
    else:
        pool = await loop_store.list(states)

    if not pool or not candidate_title:
        return None

    candidate_embedding = embedder.encode(candidate_title)
    best_match: OpenLoop | None = None
    best_score = 0.0
    for loop in pool:
        score = _cosine_similarity(candidate_embedding, embedder.encode(loop.title))
        if score > best_score:
            best_score = score
            best_match = loop

    if best_match is not None and best_score >= similarity_threshold:
        return best_match
    return None
