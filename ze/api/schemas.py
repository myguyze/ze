from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID as UUIDType

from pydantic import BaseModel, ConfigDict, Field, RootModel


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


class ConsolidationReportResponse(BaseModel):
    facts_merged: int
    facts_soft_expired: int
    facts_hard_deleted: int
    episodes_archived: int
    episodes_deleted: int
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
