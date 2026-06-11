from datetime import datetime
from typing import Any, Literal
from uuid import UUID as UUIDType

from pydantic import BaseModel, ConfigDict, RootModel


# ── REST: messages ────────────────────────────────────────────────────────────

class MessageSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDType
    role: Literal["user", "assistant"]
    text: str | None
    components: list[dict[str, Any]]
    read: bool
    thread_id: str | None
    created_at: datetime


# ── REST: capabilities ────────────────────────────────────────────────────────

CapabilityMode = Literal["autonomous", "confirm", "draft_only", "disabled"]


class CapabilityModeUpdate(BaseModel):
    mode: CapabilityMode


class AgentCapabilityConfig(BaseModel):
    """Per-agent entry from capabilities.yaml (enabled + intent modes)."""

    model_config = ConfigDict(extra="allow")

    enabled: bool | None = None


class CapabilitiesResponse(RootModel[dict[str, AgentCapabilityConfig]]):
    """Full capabilities map keyed by agent name."""


class UpdateCapabilityResponse(RootModel[dict[str, AgentCapabilityConfig]]):
    """Updated capabilities for a single agent after PUT."""


# ── REST: memory ──────────────────────────────────────────────────────────────

class UserFactResponse(BaseModel):
    id: UUIDType
    key: str
    value: str
    agent: str
    confidence: float
    reviewed: bool
    contradicted: bool
    updated_at: datetime


class FactDigestItem(BaseModel):
    id: UUIDType
    key: str
    value: str
    agent: str


class EpisodeDigestItem(BaseModel):
    id: UUIDType
    agent: str
    summary: str | None
    created_at: datetime


class ExpiringFactDigestItem(BaseModel):
    id: UUIDType
    key: str
    value: str
    agent: str
    expires_at: datetime


class MemoryDigestResponse(BaseModel):
    unreviewed_facts: list[FactDigestItem]
    contradicted_facts: list[FactDigestItem]
    recent_episodes: list[EpisodeDigestItem]
    expiring_facts: list[ExpiringFactDigestItem]


class UserProfileResponse(BaseModel):
    preferences: str
    habits: str
    topics: str
    relationships: str
    goals: str
    updated_at: datetime
    version: int


class ConsolidationReportResponse(BaseModel):
    facts_merged: int
    facts_soft_expired: int
    facts_hard_deleted: int
    episodes_archived: int
    episodes_deleted: int
    profile_updated: bool
    duration_ms: int


class FactReviewAction(BaseModel):
    id: UUIDType
    action: Literal["confirm", "reject", "edit"]
    value: str | None = None


class FactReviewRequest(BaseModel):
    actions: list[FactReviewAction]


# ── REST: routing log ─────────────────────────────────────────────────────────

class RoutingLogEntry(BaseModel):
    id: UUIDType
    session_id: str
    prompt: str
    method: str
    primary_agent: str
    confidence: float | None
    score_gap: float | None
    is_compound: bool
    raw_scores: dict[str, float] | None
    created_at: str


class ErrorDetail(BaseModel):
    detail: str | list[dict[str, Any]]


# ── REST: eval ────────────────────────────────────────────────────────────────

class EvalChatRequest(BaseModel):
    prompt: str
    session_id: str = "eval"


class EvalRoutingInfo(BaseModel):
    primary_agent: str
    confidence: float
    routing_method: str
    is_compound: bool
    score_gap: float
    raw_scores: dict[str, float]


class EvalToolCall(BaseModel):
    tool_name: str
    args: dict[str, Any]
    duration_ms: int
    success: bool
    error: str | None = None
    is_draft: bool = False


class EvalChatResponse(BaseModel):
    session_id: str
    response: str | None
    agent_used: str | None
    routing: EvalRoutingInfo | None
    pending_confirmation: bool
    error: str | None
    tool_calls: list[EvalToolCall] = []
    tokens_used: int = 0
    memory_proposals_count: int = 0
