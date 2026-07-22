from __future__ import annotations

from typing import Any
from uuid import UUID

from ze_worldstate import review
from ze_worldstate.errors import LoopNotFoundError
from ze_worldstate.store import LoopStore
from ze_worldstate.types import OpenLoop

DEFAULT_LIST_STATES = ["suspected", "active", "drifting"]


def _loop_to_list_item(loop: OpenLoop) -> dict:
    return {
        "id": loop.id,
        "title": loop.title,
        "state": loop.state.value,
        "claim_kind": loop.claim_kind.value,
        "provenance": loop.provenance.value,
        "confidence": loop.confidence,
        "created_at": loop.created_at.isoformat() if loop.created_at else None,
        "updated_at": loop.updated_at.isoformat() if loop.updated_at else None,
    }


async def list_loops(
    loop_store: LoopStore, states: list[str] | None = None
) -> list[dict]:
    effective_states = states if states is not None else DEFAULT_LIST_STATES
    loops = await loop_store.list(effective_states)
    return [_loop_to_list_item(loop) for loop in loops]


async def _fetch_evidence_summaries(
    pool: Any, loop_store: LoopStore, loop_id: UUID
) -> list[dict]:
    refs = await loop_store.list_evidence(loop_id)
    if not refs or pool is None:
        return []
    summaries: list[dict] = []
    async with pool.acquire() as conn:
        for ref in refs:
            if ref.evidence_type == "fact":
                row = await conn.fetchrow(
                    "SELECT value FROM memory_facts WHERE id = $1", ref.evidence_id
                )
                summary = row["value"] if row else ""
            elif ref.evidence_type == "episode":
                row = await conn.fetchrow(
                    "SELECT COALESCE(summary, prompt) AS s FROM memory_episodes WHERE id = $1",
                    ref.evidence_id,
                )
                summary = row["s"] if row else ""
            else:
                summary = ""
            summaries.append(
                {"type": ref.evidence_type, "id": ref.evidence_id, "summary": summary}
            )
    return summaries


async def _fetch_entities(pool: Any, loop_id: UUID) -> list[dict]:
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT me.id, me.canonical_name, me.entity_type
            FROM memory_relationships mr
            JOIN memory_entities me ON me.id = mr.source_id
            WHERE mr.target_id = $1 AND mr.target_type = 'open_loop'
              AND mr.source_type = 'entity' AND mr.predicate = 'has_open_loop'
            """,
            loop_id,
        )
    return [
        {
            "id": r["id"],
            "canonical_name": r["canonical_name"],
            "entity_type": r["entity_type"],
        }
        for r in rows
    ]


async def get_loop(loop_store: LoopStore, loop_id: UUID, pool: Any = None) -> dict:
    loop = await loop_store.get(loop_id)
    if loop is None:
        raise LoopNotFoundError(f"Loop {loop_id} not found")
    return {
        **_loop_to_list_item(loop),
        "goal_id": loop.goal_id,
        "evidence": await _fetch_evidence_summaries(pool, loop_store, loop_id),
        "entities": await _fetch_entities(pool, loop_id),
    }


def _transition_response(loop: OpenLoop) -> dict:
    return {"id": loop.id, "state": loop.state.value, "confidence": loop.confidence}


async def confirm_loop(loop_store: LoopStore, loop_id: UUID) -> dict:
    loop = await review.confirm_loop(loop_store, loop_id)
    return _transition_response(loop)


async def close_loop(loop_store: LoopStore, loop_id: UUID) -> dict:
    loop = await review.close_loop(loop_store, loop_id)
    return _transition_response(loop)


async def drop_loop(loop_store: LoopStore, loop_id: UUID) -> dict:
    loop = await review.drop_loop(loop_store, loop_id)
    return _transition_response(loop)
