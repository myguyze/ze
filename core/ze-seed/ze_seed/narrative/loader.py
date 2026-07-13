from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import yaml

from ze_core.conversation.messages.types import (
    MemoryChunkTrace,
    MessageTrace,
    ToolCallTrace,
)


@dataclass
class FactSpec:
    id: UUID
    predicate: str
    value: str
    agent: str
    confidence: float
    source_episode_id: UUID | None = None
    subject_id: UUID | None = None
    object_id: UUID | None = None
    reviewed: bool = True
    contradicted: bool = False
    provenance: str = "raw"
    days_ago: int = 0


@dataclass
class EpisodeSpec:
    id: UUID
    agent: str
    prompt: str
    response: str
    summary: str | None = None
    days_ago: int = 0


@dataclass
class ContactSpec:
    id: UUID
    name: str
    classification: str
    relationship_to_user: str
    contact_info: dict[str, str]
    notes: str
    confirmed: bool


@dataclass
class ReminderSpec:
    id: UUID
    label: str
    days_from_now: int


@dataclass
class EntitySpec:
    id: UUID
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class RelationshipSpec:
    id: UUID
    source_id: UUID
    target_id: UUID
    predicate: str
    confidence: float = 1.0


@dataclass
class MessageSpec:
    id: UUID
    role: str
    text: str
    trace: MessageTrace | None = None
    days_ago: int = 0


@dataclass
class PersonaNarrative:
    name: str
    communication_style: str
    timezone: str
    facts: list[FactSpec] = field(default_factory=list)
    episodes: list[EpisodeSpec] = field(default_factory=list)
    contacts: list[ContactSpec] = field(default_factory=list)
    reminders: list[ReminderSpec] = field(default_factory=list)
    messages: list[MessageSpec] = field(default_factory=list)
    entities: list[EntitySpec] = field(default_factory=list)
    relationships: list[RelationshipSpec] = field(default_factory=list)


def _parse_trace(data: dict) -> MessageTrace:
    chunks = [
        MemoryChunkTrace(text=c["text"], score=float(c["score"]), source=c["source"])
        for c in data.get("memory_chunks", [])
    ]
    tools = [
        ToolCallTrace(
            name=t["name"],
            result_snippet=t["result_snippet"],
            duration_ms=int(t["duration_ms"]),
            success=bool(t["success"]),
        )
        for t in data.get("tool_calls", [])
    ]
    return MessageTrace(
        agent=data["agent"],
        routing_method=data["routing_method"],
        confidence=float(data["confidence"]),
        score_gap=float(data["score_gap"]),
        is_compound=bool(data["is_compound"]),
        subtasks=list(data.get("subtasks", [])),
        memory_chunks=chunks,
        tool_calls=tools,
        total_duration_ms=int(data.get("total_duration_ms", 0)),
    )


def load_persona(path: Path | None = None) -> PersonaNarrative:
    if path is None:
        path = Path(__file__).parent / "persona.yaml"
    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    persona = raw.get("persona", {})
    facts = [
        FactSpec(
            id=UUID(item["id"]),
            predicate=item["predicate"],
            value=item["value"],
            agent=item.get("agent", "companion"),
            confidence=float(item.get("confidence", 1.0)),
            source_episode_id=UUID(item["source_episode_id"])
            if item.get("source_episode_id")
            else None,
            subject_id=UUID(item["subject_id"]) if item.get("subject_id") else None,
            object_id=UUID(item["object_id"]) if item.get("object_id") else None,
            reviewed=bool(item.get("reviewed", True)),
            contradicted=bool(item.get("contradicted", False)),
            provenance=item.get("provenance", "raw"),
            days_ago=int(item.get("days_ago", 0)),
        )
        for item in raw.get("facts", [])
    ]
    episodes = [
        EpisodeSpec(
            id=UUID(item["id"]),
            agent=item["agent"],
            prompt=item["prompt"],
            response=item["response"],
            summary=item.get("summary"),
            days_ago=int(item.get("days_ago", 0)),
        )
        for item in raw.get("episodes", [])
    ]
    contacts = [
        ContactSpec(
            id=UUID(item["id"]),
            name=item["name"],
            classification=item.get("classification", "unknown"),
            relationship_to_user=item.get("relationship_to_user", ""),
            contact_info=dict(item.get("contact_info", {})),
            notes=item.get("notes", ""),
            confirmed=bool(item.get("confirmed", False)),
        )
        for item in raw.get("contacts", [])
    ]
    reminders = [
        ReminderSpec(
            id=UUID(item["id"]),
            label=item["label"],
            days_from_now=int(item["days_from_now"]),
        )
        for item in raw.get("reminders", [])
    ]
    messages = []
    for item in raw.get("messages", []):
        trace = _parse_trace(item["trace"]) if item.get("trace") else None
        messages.append(
            MessageSpec(
                id=UUID(item["id"]),
                role=item["role"],
                text=item["text"],
                trace=trace,
                days_ago=int(item.get("days_ago", 0)),
            )
        )

    entities = [
        EntitySpec(
            id=UUID(item["id"]),
            entity_type=item["entity_type"],
            canonical_name=item["canonical_name"],
            aliases=list(item.get("aliases", [])),
            attrs=dict(item.get("attrs", {})),
        )
        for item in raw.get("entities", [])
    ]
    relationships = [
        RelationshipSpec(
            id=UUID(item["id"]),
            source_id=UUID(item["source_id"]),
            target_id=UUID(item["target_id"]),
            predicate=item["predicate"],
            confidence=float(item.get("confidence", 1.0)),
        )
        for item in raw.get("relationships", [])
    ]

    return PersonaNarrative(
        name=persona.get("name", "Alex"),
        communication_style=persona.get("communication_style", "direct"),
        timezone=persona.get("timezone", "UTC"),
        facts=facts,
        episodes=episodes,
        contacts=contacts,
        reminders=reminders,
        messages=messages,
        entities=entities,
        relationships=relationships,
    )
