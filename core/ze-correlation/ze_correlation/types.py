from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID


@dataclass
class EvidenceRef:
    kind: Literal["fact", "episode", "signal"]
    id: UUID
    label: str                # short human label, e.g. "Fable 5 ban (Jun 12)"
    external_ref: str | None  # source url/id when the evidence is a signal-event
    origin: Literal["graph_recall", "live_search", "prompt_supplied"]
    retrieved_at: datetime    # when this piece entered the neighbourhood
    ingested_at: datetime | None = None  # when it first entered memory (graph_recall only)


@dataclass
class Hypothesis:
    id: UUID
    summary: str              # one-line connection, neutral and hedged
    narrative: str            # the reasoning, with uncertainty made explicit
    relation: Literal["pattern", "causal_guess", "tension", "convergence"]
    confidence: float         # LLM self-rating, 0..1
    relevance: float          # Phase 56 RelevanceScore.value
    evidence: list[EvidenceRef]
    entities: list[UUID]      # seed entity IDs
    created_at: datetime
    surfaced: bool = False    # True when shown inline or pushed
    feedback: Literal["useful", "not_relevant", "muted"] | None = None
