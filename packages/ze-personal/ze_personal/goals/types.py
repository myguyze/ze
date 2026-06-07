from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SuggestionStatus(StrEnum):
    PENDING   = "pending"
    ACCEPTED  = "accepted"
    DISMISSED = "dismissed"
    EXPIRED   = "expired"


@dataclass
class GoalSuggestion:
    id: UUID
    title: str
    objective: str
    rationale: str
    source_type: str
    source_ref: str
    status: SuggestionStatus
    suggested_at: datetime
    resolved_at: datetime | None = None
    created_goal_id: UUID | None = None


class GoalStatus(StrEnum):
    PLANNING      = "planning"
    ACTIVE        = "active"
    AWAITING_GATE = "awaiting_gate"
    PAUSED        = "paused"
    COMPLETED     = "completed"
    ABANDONED     = "abandoned"


class MilestoneStatus(StrEnum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    SKIPPED     = "skipped"


class GateStatus(StrEnum):
    PENDING           = "pending"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED          = "approved"
    STOPPED           = "stopped"
    REDIRECTED        = "redirected"


@dataclass
class Goal:
    title: str
    objective: str
    success_condition: str
    status: GoalStatus = GoalStatus.PLANNING
    type: str = "custom"
    time_horizon: str = ""
    learnings: str = ""
    retrospective_text: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Milestone:
    goal_id: UUID
    title: str
    description: str
    sequence: int
    agent_hint: str | None = None
    intent: str = "execute"
    status: MilestoneStatus = MilestoneStatus.PENDING
    output: str = ""
    id: UUID | None = None
    completed_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class VerificationGate:
    goal_id: UUID
    after_sequence: int
    title: str
    status: GateStatus = GateStatus.PENDING
    context_summary: str = ""
    plan_summary: str = ""
    user_feedback: str = ""
    id: UUID | None = None
    fired_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime | None = None


@dataclass
class GoalLearning:
    goal_id: UUID
    content: str
    source: str
    id: UUID | None = None
    created_at: datetime | None = None


@dataclass
class ExecutionTrace:
    milestone_id: UUID
    goal_id: UUID
    seq: int
    tool_name: str
    args: dict
    result: str
    duration_ms: int
    success: bool
    error: str | None = None
    id: UUID | None = None
    created_at: datetime | None = None
