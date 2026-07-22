from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class LoopState(StrEnum):
    SUSPECTED = "suspected"
    ACTIVE = "active"
    DRIFTING = "drifting"
    CLOSED = "closed"
    DROPPED = "dropped"


class LoopClaimKind(StrEnum):
    IDENTITY = "identity"
    FACT = "fact"
    INFERENCE = "inference"
    SUSPICION = "suspicion"
    PRIORITY = "priority"


class LoopProvenance(StrEnum):
    CONVERSATION = "conversation"
    EMAIL = "email"
    CALENDAR = "calendar"
    INGESTION = "ingestion"
    USER_DECLARED = "user_declared"


@dataclass
class OpenLoop:
    title: str
    claim_kind: LoopClaimKind
    provenance: LoopProvenance
    confidence: float
    state: LoopState = LoopState.SUSPECTED
    goal_id: UUID | None = None
    dismissed_evidence_fingerprint: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    confirmed_at: datetime | None = None
    closed_at: datetime | None = None


@dataclass
class EvidenceRef:
    evidence_type: str  # "fact" | "episode"
    evidence_id: UUID
