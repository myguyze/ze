"""Graph layer data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass
class Relationship:
    """A durable, provenanced edge in the memory graph.

    Every relationship must carry provenance_id or creation_method='extracted'|'synthesized'
    to be considered durable. Relationships created without provenance are ephemeral.
    """
    source_id: UUID
    source_type: str
    predicate: str
    id: UUID | None = None
    target_id: UUID | None = None
    target_type: str | None = None
    target_text: str | None = None
    confidence: float = 1.0
    provenance_id: UUID | None = None
    creation_method: str = "explicit"   # explicit | extracted | synthesized
    reviewed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GraphExpansion:
    """The result of a bounded graph traversal from a set of seed node IDs.

    IDs are partitioned by type so callers can fetch additional rows from the
    appropriate tables without re-querying relationships.
    """
    relationships: list[Relationship] = field(default_factory=list)
    fact_ids: list[UUID] = field(default_factory=list)
    entity_ids: list[UUID] = field(default_factory=list)
    episode_ids: list[UUID] = field(default_factory=list)
    procedure_ids: list[UUID] = field(default_factory=list)
    signal_ids: list[UUID] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.relationships
            or self.fact_ids
            or self.entity_ids
            or self.episode_ids
            or self.procedure_ids
            or self.signal_ids
        )
