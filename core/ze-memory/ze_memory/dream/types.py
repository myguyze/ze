from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class ArtifactType(str, Enum):
    SCHEMA_CANDIDATE = "schema_candidate"
    POLICY_CANDIDATE = "policy_candidate"
    SYNTHESIZED_INSIGHT = "synthesized_insight"
    SYNTHESIZED_PROCEDURE = "synthesized_procedure"
    HINDSIGHT_FACT = "hindsight_fact"
    PLAN_STRESS_TEST = "plan_stress_test"
    COUNTERFACTUAL = "counterfactual"
    PERTURBATION_CHECK = "perturbation_check"


class ArtifactStatus(str, Enum):
    PENDING = "pending"
    CRITIC_ONLY = "critic_only"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    NEEDS_REVIEW = "needs_review"
    REVISED = "revised"
    ROLLED_BACK = "rolled_back"


@dataclass
class DreamArtifact:
    id: UUID
    run_id: UUID
    artifact_type: ArtifactType
    content: str
    source_episode_ids: list[UUID]
    source_fact_ids: list[UUID]
    support_count: int
    distinct_session_count: int
    temporal_spread_days: int
    user_asserted_source_count: int
    faithfulness_score: Optional[float]
    novelty_score: Optional[float]
    retrievable: Optional[bool]
    critic_a_verdict: Optional[str]
    critic_a_reason: Optional[str]
    critic_b_verdict: Optional[str]
    critic_b_reason: Optional[str]
    status: ArtifactStatus
    user_revised_content: Optional[str]
    promoted_to: Optional[str]
    promoted_id: Optional[UUID]
    created_at: datetime
    reviewed_at: Optional[datetime]


@dataclass
class DreamRun:
    id: UUID
    started_at: datetime
    finished_at: Optional[datetime]
    episodes_scored: int
    episodes_replayed: int
    artifacts_generated: int
    artifacts_promoted: int
    artifacts_rejected: int
    artifacts_pending_review: int
    sleep_pass_duration_ms: int
    dream_pass_duration_ms: int
    integration_duration_ms: int
    error: Optional[str]


@dataclass
class ReplayCandidate:
    episode_id: UUID
    replay_score: float
    recency_score: float
    novelty_score: float
    confidence_inverse_score: float


@dataclass
class DreamJournalEntry:
    run_id: UUID
    summary: str
    episodes_processed: int
    insights_promoted: int
    procedures_extracted: int
    plan_risks_surfaced: int
    pending_review: int
    created_at: datetime
