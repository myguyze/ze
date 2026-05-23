from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


SOURCE_WEIGHTS: dict[str, float] = {
    "manual": 1.0,
    "conversation": 1.0,
    "email": 0.7,
    "calendar": 0.6,
    "research": 0.2,
}


@dataclass
class Person:
    name: str
    aliases: list[str] = field(default_factory=list)
    classification: str = "unknown"          # "personal" | "professional" | "unknown"
    classification_confidence: float = 0.0
    relationship_to_user: str = ""           # free text Ze infers from context
    contact_info: dict[str, str] = field(default_factory=dict)
    notes: str = ""
    confirmed: bool = False
    dismissed: bool = False
    confidence: float = 0.0                  # max(source.weight) across all sources
    id: UUID | None = None
    first_seen: datetime | None = None
    last_mentioned: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class PersonSource:
    person_id: UUID
    source_type: str                         # "conversation" | "manual" | "email" | "calendar" | "research"
    weight: float
    raw_context: str = ""
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class PersonRelationship:
    person_a_id: UUID
    person_b_id: UUID
    relationship_description: str            # free text: "works at same company as João"
    confidence: float = 0.5
    source_type: str = "manual"
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class PersonCandidate:
    """Intermediate type produced by extraction — not yet stored as a Person."""
    name: str
    inferred_classification: str = "unknown"
    inferred_relationship: str = ""
    raw_context: str = ""
    source_type: str = "research"


@dataclass
class PersonContext:
    people: list[Person] = field(default_factory=list)
    token_estimate: int = 0


@dataclass
class ContactsConsolidationReport:
    episodes_scanned: int = 0
    candidates_extracted: int = 0
    contacts_created: int = 0
    contacts_updated: int = 0
    duration_ms: int = 0
