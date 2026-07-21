from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Union
from uuid import UUID as UUIDType

from pydantic import BaseModel, ConfigDict, Field, RootModel


# ── REST: health ──────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: Literal["ok"]


# ── REST: sessions ────────────────────────────────────────────────────────────


class SessionSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str | None
    preview: str | None
    title_source: Literal["user", "generated"] | None = None
    created_at: datetime
    last_active_at: datetime


class SessionListResponse(BaseModel):
    items: list[SessionSchema]
    next_before: datetime | None


class SessionSearchResult(BaseModel):
    id: str
    title: str | None
    preview: str | None
    title_source: Literal["user", "generated"] | None = None
    created_at: datetime
    last_active_at: datetime
    match_source: Literal["message", "metadata", "summary"]
    snippet: str | None
    rank: float


class CreateSessionRequest(BaseModel):
    id: str | None = None
    title: str | None = None


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


# ── REST: message trace ───────────────────────────────────────────────────────


class MemoryChunkTraceResponse(BaseModel):
    text: str
    score: float
    source: str
    extraction_confidence: float | None = None


class ToolCallTraceResponse(BaseModel):
    name: str
    result_snippet: str
    duration_ms: int
    success: bool


class MessageTraceResponse(BaseModel):
    agent: str
    routing_method: str
    confidence: float
    score_gap: float
    is_compound: bool
    subtasks: list[str]
    memory_chunks: list[MemoryChunkTraceResponse]
    tool_calls: list[ToolCallTraceResponse]
    total_duration_ms: int


class MessageTraceEntry(BaseModel):
    message_id: UUIDType
    trace: MessageTraceResponse


class MessageTracesResponse(BaseModel):
    traces: list[MessageTraceEntry]


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
    session_episodes_archived: int
    profile_updated: bool
    duration_ms: int


class MemoryFactQualityResponse(BaseModel):
    total: int
    by_provenance: dict[str, int]
    avg_confidence: float
    low_confidence_count: int
    contradicted_count: int
    synthesized_unreviewed: int
    synthesized_uncorroborated: int
    synthesized_expired: int


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


# ── REST: web data screens ────────────────────────────────────────────────────


class GoalListItem(BaseModel):
    id: UUIDType
    title: str
    objective: str
    status: str
    created_at: datetime


class GoalActionResponse(BaseModel):
    id: UUIDType
    status: str


class MilestoneResponse(BaseModel):
    id: UUIDType
    title: str
    description: str
    sequence: int
    status: str
    output: str | None
    reuse_hint: str | None
    completed_at: datetime | None
    created_at: datetime


class GateResponse(BaseModel):
    id: UUIDType
    after_sequence: int
    title: str
    status: str
    context_summary: str | None
    plan_summary: str | None
    user_feedback: str | None
    fired_at: datetime | None
    resolved_at: datetime | None


class LearningResponse(BaseModel):
    id: UUIDType
    content: str
    source: str
    created_at: datetime


class GoalDetailResponse(BaseModel):
    id: UUIDType
    title: str
    objective: str
    success_condition: str
    status: str
    type: str
    time_horizon: str | None
    learnings_summary: str | None
    retrospective_text: str | None
    created_at: datetime
    updated_at: datetime
    milestones: list[MilestoneResponse]
    gates: list[GateResponse]
    learnings: list[LearningResponse]


class ExecutionTraceResponse(BaseModel):
    id: UUIDType
    milestone_id: UUIDType
    goal_id: UUIDType
    seq: int
    tool_name: str
    args: dict
    result: str
    duration_ms: int
    success: bool
    error: str | None
    created_at: datetime


class AgentCostBucket(BaseModel):
    usd: float
    tokens: int
    calls: int
    prompt_tokens: int
    completion_tokens: int


class DailyCostBucket(BaseModel):
    date: str
    usd: float
    calls: int


class CostAnomalyItem(BaseModel):
    agent: str
    run_cost_usd: float
    baseline_cost_usd: float
    multiplier: float
    session_id: str | None
    detected_at: str


class CostAnomaliesResponse(BaseModel):
    anomalies: list[CostAnomalyItem]
    period_days: int


class WebCostSummaryResponse(BaseModel):
    total_usd: float
    total_tokens: int
    total_calls: int
    by_agent: dict[str, AgentCostBucket]
    by_plugin: dict[str, AgentCostBucket]
    by_day: list[DailyCostBucket]
    period: str


class CredibilityFlagItem(BaseModel):
    type: str
    label: str
    detail: str


class ArticleItem(BaseModel):
    url: str
    source_key: str
    title: str
    summary: str
    published_at: datetime
    tags: list[str]
    credibility_flags: list[CredibilityFlagItem]


# ── REST: data portability ────────────────────────────────────────────────────


class DataDomainItem(BaseModel):
    name: str
    importable: bool
    count: int | None
    size_bytes: int


class DataDomainsResponse(BaseModel):
    domains: list[DataDomainItem]
    schema_revisions: list[str]
    total_records: int
    total_size_bytes: int


class DeleteIntentResponse(BaseModel):
    confirmation_token: str
    expires_at: str


class DeleteRequest(BaseModel):
    confirmation_token: str


class ImportResponse(BaseModel):
    domains_imported: list[str]
    rows_imported: dict[str, int]


# ── REST: workflows ───────────────────────────────────────────────────────────


class BranchResponse(BaseModel):
    condition: str
    to: str


class StepResultResponse(BaseModel):
    step_index: int
    task: str
    output: str
    success: bool
    error: str | None
    duration_ms: int
    step_id: str
    branch_taken: str | None
    attempt_count: int = 1
    no_results: bool = False


class BranchInput(BaseModel):
    condition: str
    to: str


class WorkflowStepResponse(BaseModel):
    task: str
    agent_hint: str | None
    verify: str | None
    id: str
    branches: list[BranchResponse]
    default_next: str | None
    on_failure: str = "fail"


class WorkflowStepInput(BaseModel):
    task: str
    agent_hint: str | None = None
    verify: str | None = None
    intent: str = "execute"
    id: str
    branches: list[BranchInput] = []
    default_next: str | None = None
    on_failure: str = "fail"


class UpdateWorkflowStepsRequest(BaseModel):
    steps: list[WorkflowStepInput]


class WorkflowResponse(BaseModel):
    id: UUIDType
    name: str
    description: str
    schedule: str | None
    enabled: bool
    last_run_at: str | None
    next_run_at: str | None
    created_at: str


class WorkflowDetailResponse(WorkflowResponse):
    steps: list[WorkflowStepResponse]


class WorkflowExecutionResponse(BaseModel):
    id: UUIDType
    workflow_id: UUIDType | None
    status: str
    step_results: list[StepResultResponse]
    steps_snapshot: list[WorkflowStepResponse] = []
    error: str | None
    summary: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str


class TriggerWorkflowResponse(BaseModel):
    status: str
    workflow_id: UUIDType
    execution_id: UUIDType


class CancelWorkflowExecutionResponse(BaseModel):
    status: Literal["cancelled", "not_running"]
    execution_id: UUIDType
    message: str


class ActorContextResponse(BaseModel):
    source: Literal["agent", "api", "system"]
    session_id: str | None = None
    user_message_id: str | None = None


class WorkflowRevisionResponse(BaseModel):
    id: UUIDType
    workflow_id: UUIDType
    revision_number: int
    change_type: Literal["created", "edited"]
    steps_before: list[WorkflowStepResponse]
    steps_after: list[WorkflowStepResponse]
    summary: str
    actor_source: Literal["agent", "api", "system"]
    actor_session_id: str | None = None
    actor_user_message_id: str | None = None
    created_at: str


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


# ── WebSocket protocol — Server → Client (inbound frames) ─────────────────────


class OnboardingMeta(BaseModel):
    session_id: str
    completed: bool


class WsConfirmAction(BaseModel):
    label: str
    value: str
    style: Literal["primary", "secondary", "danger"] | None = None


class WsMessageFrame(BaseModel):
    type: Literal["message"]
    message: MessageSchema
    onboarding: OnboardingMeta | None = None


class WsEditFrame(BaseModel):
    type: Literal["edit"]
    id: str
    thread_id: str | None = None
    text: str | None = None
    components: list[dict[str, Any]] = []


class WsConfirmRequestFrame(BaseModel):
    type: Literal["confirm_request"]
    id: str
    thread_id: str | None = None
    prompt: str
    actions: list[WsConfirmAction]


class WsConfirmCancelFrame(BaseModel):
    type: Literal["confirm_cancel"]
    id: str
    thread_id: str | None = None


class WsTypingFrame(BaseModel):
    type: Literal["typing"]
    thread_id: str | None = None
    text: str | None = None


class WsTokenFrame(BaseModel):
    type: Literal["token"]
    thread_id: str | None = None
    text: str


class WsErrorFrame(BaseModel):
    type: Literal["error"]
    thread_id: str | None = None
    detail: str


class WsRefreshFrame(BaseModel):
    type: Literal["refresh"]
    thread_id: str | None = None
    screen: str


class WsPongFrame(BaseModel):
    type: Literal["pong"]


class WsTraceUpdateFrame(BaseModel):
    type: Literal["trace_update"]
    thread_id: str | None = None
    message_id: str
    partial: bool = False
    agent: str
    routing_method: str
    confidence: float
    score_gap: float
    is_compound: bool
    subtasks: list[str]
    memory_chunks: list[MemoryChunkTraceResponse]
    tool_calls: list[ToolCallTraceResponse]
    total_duration_ms: int


class WsNotificationFrame(BaseModel):
    type: Literal["notification"]
    id: str
    event_type: str
    source: str
    title: str
    body: str
    target_type: str | None
    target_id: str | None
    created_at: datetime
    read: bool = False


WsInboundFrame = Annotated[
    Union[
        WsMessageFrame,
        WsEditFrame,
        WsConfirmRequestFrame,
        WsConfirmCancelFrame,
        WsTypingFrame,
        WsTokenFrame,
        WsErrorFrame,
        WsRefreshFrame,
        WsPongFrame,
        WsTraceUpdateFrame,
        WsNotificationFrame,
    ],
    Field(discriminator="type"),
]


# ── WebSocket protocol — Client → Server (outbound frames) ────────────────────


class WsScreenContext(BaseModel):
    screen: str
    goal_id: str | None = None
    workflow_id: str | None = None
    execution_id: str | None = None


class WsSendMessageFrame(BaseModel):
    type: Literal["message"]
    text: str
    thread_id: str | None = None
    context: WsScreenContext | None = None


class WsAckFrame(BaseModel):
    type: Literal["ack"]
    ids: list[str]


class WsConfirmFrame(BaseModel):
    type: Literal["confirm"]
    id: str
    thread_id: str
    choice: Literal["approve", "deny"]


class WsActionFrame(BaseModel):
    type: Literal["action"]
    payload: str
    thread_id: str | None = None


class WsCommandFrame(BaseModel):
    type: Literal["command"]
    name: Literal[
        "cancel",
        "costs",
        "capabilities",
        "status",
        "onboarding",
        "reset",
        "reset_preview",
    ]


class WsComponentSubmitFrame(BaseModel):
    type: Literal["component_submit"]
    step_id: str
    values: dict[str, Any]
    session_id: str | None = None
    thread_id: str | None = None


class WsPingFrame(BaseModel):
    type: Literal["ping"]


WsOutboundFrame = Annotated[
    Union[
        WsSendMessageFrame,
        WsAckFrame,
        WsConfirmFrame,
        WsActionFrame,
        WsCommandFrame,
        WsComponentSubmitFrame,
        WsPingFrame,
    ],
    Field(discriminator="type"),
]


class WsSchemaResponse(BaseModel):
    inbound: dict[str, Any]
    outbound: dict[str, Any]


# ── REST: dream memory ─────────────────────────────────────────────────────────


class DreamJournalEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDType
    run_id: UUIDType
    summary: str
    episodes_processed: int
    insights_promoted: int
    procedures_extracted: int
    plan_risks_surfaced: int
    pending_review: int
    created_at: datetime


class DreamArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUIDType
    run_id: UUIDType
    artifact_type: str
    content: str
    source_episode_ids: list[UUIDType]
    source_fact_ids: list[UUIDType]
    support_count: int
    distinct_session_count: int
    temporal_spread_days: int
    user_asserted_source_count: int
    faithfulness_score: float | None
    novelty_score: float | None
    retrievable: bool | None
    critic_a_verdict: str | None
    critic_a_reason: str | None
    critic_b_verdict: str | None
    critic_b_reason: str | None
    status: str
    user_revised_content: str | None
    promoted_to: str | None
    promoted_id: UUIDType | None
    created_at: datetime
    reviewed_at: datetime | None


class DreamReviseRequest(BaseModel):
    content: str


class DreamRollbackResponse(BaseModel):
    rolled_back: int
    summaries_flagged: int


# ── REST: memory feed ─────────────────────────────────────────────────────────


class MemoryFeedItem(BaseModel):
    id: UUIDType
    type: Literal["fact", "episode"]
    key: str | None
    value: str | None
    confidence: float | None
    reviewed: bool | None
    contradicted: bool | None
    provenance: str | None
    summary: str | None
    prompt_snippet: str | None
    agent: str
    created_at: datetime


class MemoryFeedResponse(BaseModel):
    items: list[MemoryFeedItem]
    next_before: datetime | None
    total_facts: int | None = None
    total_episodes: int | None = None


class TimelineBoundsResponse(BaseModel):
    earliest: datetime | None
    latest: datetime


class MemoryActivityDay(BaseModel):
    date: str
    count: int


class MemoryActivityResponse(BaseModel):
    days: list[MemoryActivityDay]
    max_count: int


# ── REST: channels ────────────────────────────────────────────────────────────


class ChannelInfo(BaseModel):
    channel_id: str
    channel_type: str
    handle: str
    display_name: str | None
    is_default_outbound: bool
    poll_enabled: bool
    supports_push: bool
    last_polled_at: datetime | None


class ChannelListResponse(BaseModel):
    channels: list[ChannelInfo]


class ChannelUpdateRequest(BaseModel):
    poll_enabled: bool | None = None
    is_default_outbound: bool | None = None
    display_name: str | None = None


class ChannelResponse(BaseModel):
    channel: ChannelInfo


# ── REST: UI manifest ─────────────────────────────────────────────────────────


class UiContributionSchema(BaseModel):
    id: str
    plugin: str
    kind: Literal["nav", "settings_section"]
    label: str
    icon: str
    path: str | None = None
    page_operation_id: str | None = None
    settings_operation_id: str | None = None
    priority: int = 100
    show_in_mobile_nav: bool = True


class UiManifestResponse(BaseModel):
    nav: list[UiContributionSchema]
    settings_sections: list[UiContributionSchema]

    @classmethod
    def from_domain(cls, manifest) -> UiManifestResponse:
        def to_schema(item) -> UiContributionSchema:
            return UiContributionSchema(
                id=item.id,
                plugin=item.plugin,
                kind=item.kind,
                label=item.label,
                icon=item.icon,
                path=item.path,
                page_operation_id=item.page_operation_id,
                settings_operation_id=item.settings_operation_id,
                priority=item.priority,
                show_in_mobile_nav=item.show_in_mobile_nav,
            )

        return cls(
            nav=[to_schema(item) for item in manifest.nav],
            settings_sections=[to_schema(item) for item in manifest.settings_sections],
        )


# ── REST: activity heatmap ────────────────────────────────────────────────────


class AgentDayCount(BaseModel):
    agent: str
    count: int


class HeatmapDay(BaseModel):
    date: str
    total: int
    agents: list[AgentDayCount]


class ActivityHeatmapResponse(BaseModel):
    days: list[HeatmapDay]
    agents: list[str]
    start: str
    end: str


# ── REST: memory graph ────────────────────────────────────────────────────────


class GraphEntityNode(BaseModel):
    id: UUIDType
    entity_type: str
    canonical_name: str
    aliases: list[str]
    attrs: dict
    degree: int


class GraphEdge(BaseModel):
    id: UUIDType
    source_id: UUIDType
    target_id: UUIDType
    predicate: str
    confidence: float


class MemoryGraphResponse(BaseModel):
    nodes: list[GraphEntityNode]
    edges: list[GraphEdge]


class EntityDetailResponse(BaseModel):
    entity: GraphEntityNode
    facts: list[FactDigestItem]
    episodes: list[EpisodeDigestItem]
    neighbours: list[GraphEntityNode]
    neighbour_edges: list[GraphEdge]


# ── REST: notifications ──────────────────────────────────────────────────────


class NotificationItem(BaseModel):
    id: str
    event_type: str
    source: str
    title: str
    body: str
    target_type: str | None
    target_id: str | None
    created_at: datetime
    read: bool


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    next_cursor: str | None


class UnreadCountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    marked: int
