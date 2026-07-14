from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from ze_agents.types import RetrievalRequest as RetrievalRequest  # noqa: F401 — re-export


@dataclass
class EntityRef:
    name: str
    entity_type: str  # "person" | "org" | "topic" | "ticker" | "place" | "product"


@dataclass
class RelevanceEntry:
    key: str  # entity id or normalized topic
    kind: Literal["entity", "topic"]
    weight: float  # 0..1
    sources: list[str]  # why: ["profile:topics", "goal:...", "episode:recent"]


@dataclass
class RelevanceSet:
    entries: dict[str, RelevanceEntry]
    built_at: datetime


@dataclass
class RelevanceScore:
    value: float  # 0..1
    contributions: list[str]  # explainable: matched keys and their weights


@dataclass
class Signal:
    id: UUID
    source: str  # plugin/source key, e.g. "news"
    external_ref: str  # stable id in the source store (article URL, etc.)
    title: str
    summary: str
    occurred_at: datetime
    entities: list[EntityRef] = field(default_factory=list)
    magnitude: float = 0.0
    payload: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None


@dataclass
class SignalIngestResult:
    signal_id: UUID
    entity_ids: list[UUID]
    created: bool  # False if deduped to an existing signal


@dataclass
class Entity:
    id: UUID | None
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    embedding: Any = field(default=None, repr=False, compare=False)
    relevance_score: float | None = field(default=None, compare=False)
    retrieval_provenance: str | None = field(default=None, compare=False)


@dataclass
class Fact:
    predicate: str
    value: str
    id: UUID | None = None
    subject_id: UUID | None = None
    object_text: str | None = None
    object_id: UUID | None = None
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    source_episode_id: UUID | None = None
    source_refs: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)
    provenance: str = "raw"
    agent: str = "unknown"
    relevance_score: float | None = field(default=None, compare=False)
    retrieval_provenance: str | None = field(default=None, compare=False)


@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    id: UUID | None = None
    session_id: str = ""
    summary: str | None = None
    relevance: float = 0.0
    created_at: datetime | None = None
    linked_entity_ids: list[UUID] = field(default_factory=list)
    linked_fact_ids: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)
    relevance_score: float | None = field(default=None, compare=False)
    retrieval_provenance: str | None = field(default=None, compare=False)


@dataclass
class SessionSummary:
    id: UUID
    session_id: str
    summary: str
    episode_count: int
    last_turn_at: datetime
    created_at: datetime
    summary_updated_at: datetime
    embedding: Any = field(default=None, repr=False, compare=False)
    relevance_score: float | None = field(default=None, compare=False)


@dataclass
class Event:
    id: UUID | None
    event_type: str
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    participant_names: list[str] = field(
        default_factory=list
    )  # unresolved names from extraction
    participants: list[UUID] = field(default_factory=list)  # resolved Entity ids
    roles: dict[str, UUID] = field(default_factory=dict)
    summary: str | None = None
    outcome: str | None = None
    source_episode_id: UUID | None = None
    embedding: Any = field(default=None, repr=False, compare=False)
    relevance_score: float | None = field(default=None, compare=False)
    retrieval_provenance: str | None = field(default=None, compare=False)


@dataclass
class Procedure:
    id: UUID | None
    name: str
    trigger: str
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    version: int = 1
    source_refs: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)


@dataclass
class TaskState:
    id: UUID | None
    task_id: UUID | None
    goal_id: UUID | None
    status: str
    open_steps: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    last_action: str | None = None
    next_action: str | None = None
    tool_cursors: dict[str, str] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass
class ProfileFacet:
    key: str
    value: str
    stability: str
    confidence: float = 1.0
    source_refs: list[UUID] = field(default_factory=list)
    updated_at: datetime | None = None


@dataclass
class MemoryContext:
    facts: list[Fact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    session_summaries: list[SessionSummary] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    task_state: TaskState | None = None
    profile: list[ProfileFacet] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    token_estimate: int = 0


@dataclass
class RetrievalCacheEntry:
    session_id: str
    query_hash: str
    fact_ranked_ids: list[UUID]
    summary_ranked_ids: list[UUID]
    created_at: datetime


@dataclass
class ConsolidationReport:
    facts_merged: int = 0
    facts_soft_expired: int = 0
    facts_hard_deleted: int = 0
    episodes_archived: int = 0
    episodes_deleted: int = 0
    session_episodes_archived: int = 0
    profile_updated: bool = False
    duration_ms: int = 0
