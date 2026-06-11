"""Helpers for building MemoryContext projections from database rows."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from ze_memory.types import (
    Entity,
    Episode,
    Event,
    Fact,
    MemoryContext,
    Procedure,
    ProfileFacet,
    TaskState,
)


def budget_facts(rows: list[Any], budget_tokens: int) -> list[Fact]:
    facts: list[Fact] = []
    used = 0
    for row in rows:
        cost = len(row["value"]) // 4
        if used + cost > budget_tokens:
            break
        facts.append(_fact_from_row(row))
        used += cost
    return facts


def budget_episodes(rows: list[Any], budget_tokens: int) -> list[Episode]:
    episodes: list[Episode] = []
    used = 0
    for row in rows:
        text = row["summary"] or row["response"][:200]
        cost = len(text) // 4
        if used + cost > budget_tokens:
            break
        episodes.append(_episode_from_row(row))
        used += cost
    return episodes


def facets_from_rows(rows: list[Any], budget_tokens: int) -> list[ProfileFacet]:
    facets: list[ProfileFacet] = []
    used = 0
    for row in rows:
        cost = len(row["value"]) // 4
        if used + cost > budget_tokens:
            break
        facets.append(_facet_from_row(row))
        used += cost
    return facets


def procedures_from_rows(rows: list[Any], budget_tokens: int) -> list[Procedure]:
    procs: list[Procedure] = []
    used = 0
    for row in rows:
        steps = _load_json(row["steps"])
        cost = sum(len(s) // 4 for s in steps)
        if used + cost > budget_tokens:
            break
        procs.append(_procedure_from_row(row))
        used += cost
    return procs


def task_state_from_row(row: Any) -> TaskState:
    return TaskState(
        id=row["id"],
        task_id=row["task_id"],
        goal_id=row["goal_id"],
        status=row["status"],
        open_steps=_load_json(row["open_steps"]),
        blocked_by=_load_json(row["blocked_by"]),
        last_action=row["last_action"],
        next_action=row["next_action"],
        tool_cursors=_load_json(row["tool_cursors"]),
        updated_at=row["updated_at"],
    )


def events_from_rows(rows: list[Any]) -> list[Event]:
    return [_event_from_row(row) for row in rows]


def entities_from_rows(rows: list[Any]) -> list[Entity]:
    return [_entity_from_row(row) for row in rows]


def token_estimate(ctx: MemoryContext) -> int:
    fact_tokens = sum(len(f.value) // 4 for f in ctx.facts)
    episode_tokens = sum(len(e.summary or e.response[:200]) // 4 for e in ctx.episodes)
    profile_tokens = sum(len(p.value) // 4 for p in ctx.profile)
    proc_tokens = sum(sum(len(s) // 4 for s in p.steps) for p in ctx.procedures)
    event_tokens = sum(len(e.title) // 4 for e in ctx.events)
    return fact_tokens + episode_tokens + profile_tokens + proc_tokens + event_tokens


def _fact_from_row(row: Any) -> Fact:
    return Fact(
        predicate=row["predicate"],
        value=row["value"],
        id=row["id"],
        subject_id=row["subject_id"],
        object_text=row["object_text"],
        object_id=row["object_id"],
        confidence=row["confidence"],
        reviewed=row["reviewed"],
        contradicted=row["contradicted"],
        source_episode_id=row["source_episode_id"],
        source_refs=_load_uuids(row["source_refs"]),
    )


def _episode_from_row(row: Any) -> Episode:
    return Episode(
        agent=row["agent"],
        prompt=row["prompt"],
        response=row["response"],
        id=row["id"],
        session_id=row["session_id"] or "",
        summary=row["summary"],
        relevance=row["relevance"],
        created_at=row["created_at"],
        linked_entity_ids=_load_uuids(row["linked_entity_ids"]),
        linked_fact_ids=_load_uuids(row["linked_fact_ids"]),
    )


def _facet_from_row(row: Any) -> ProfileFacet:
    return ProfileFacet(
        key=row["key"],
        value=row["value"],
        stability=row["stability"],
        confidence=row["confidence"],
        source_refs=_load_uuids(row["source_refs"]),
        updated_at=row["updated_at"],
    )


def _event_from_row(row: Any) -> Event:
    return Event(
        id=row["id"],
        event_type=row["event_type"],
        title=row["title"],
        start_at=row.get("start_at"),
        end_at=row.get("end_at"),
        participant_names=_load_json(row.get("participant_names") or "[]"),
        participants=_load_uuids(row.get("participants") or "[]"),
        roles=_load_json(row.get("roles") or "{}"),
        summary=row.get("summary"),
        outcome=row.get("outcome"),
        source_episode_id=row.get("source_episode_id"),
    )


def _entity_from_row(row: Any) -> Entity:
    return Entity(
        id=row["id"],
        entity_type=row["entity_type"],
        canonical_name=row["canonical_name"],
        aliases=_load_json(row["aliases"]),
        attrs=_load_json(row["attrs"]),
    )


def _procedure_from_row(row: Any) -> Procedure:
    return Procedure(
        id=row["id"],
        name=row["name"],
        trigger=row["trigger"],
        preconditions=_load_json(row["preconditions"]),
        steps=_load_json(row["steps"]),
        success_criteria=_load_json(row["success_criteria"]),
        version=row["version"],
        source_refs=_load_uuids(row["source_refs"]),
    )


def _load_json(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return []


def _load_uuids(value: Any) -> list[UUID]:
    raw = _load_json(value)
    result = []
    for item in raw:
        try:
            result.append(UUID(str(item)))
        except (ValueError, AttributeError):
            pass
    return result
