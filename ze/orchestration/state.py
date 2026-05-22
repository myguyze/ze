from typing import TypedDict
from uuid import UUID

from ze.agents.types import AgentContext, AgentResult
from ze.capability.types import GateDecision
from ze.memory.types import MemoryContext
from ze.routing.types import RoutingEnvelope


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]  # "agent.intent" → mode string

    # ── Multimodal ─────────────────────────────────────────────────────────
    input_modality: str        # "text" | "voice" | "image" — default "text"
    image_data: bytes | None   # raw image bytes; None for text/voice turns
    image_mime: str | None     # "image/jpeg" | "image/png" | None
    image_caption: str | None  # routing caption generated at embed_route; None until set

    # ── Routing ────────────────────────────────────────────────────────────
    envelope: RoutingEnvelope | None

    # ── Context ────────────────────────────────────────────────────────────
    memory_context: MemoryContext | None
    agent_context: AgentContext | None

    # ── Capability ─────────────────────────────────────────────────────────
    gate_decision: GateDecision | None

    # ── Execution ──────────────────────────────────────────────────────────
    agent_result: AgentResult | None
    subtask_results: list[AgentResult]
    pending_confirmation: bool

    # ── Conversation history ───────────────────────────────────────────────
    messages: list[dict]         # rolling window of completed turns (user+assistant pairs)
    last_active_at: float | None  # unix timestamp of last processed message

    # ── Workflow execution ─────────────────────────────────────────────────
    workflow_id: UUID | None
    workflow_execution_id: UUID | None
    workflow_steps: list | None          # list[WorkflowStep] — untyped to avoid circular import
    current_step_index: int
    workflow_step_results: list          # list[StepResult]

    # ── Dynamic plan (Mode 3) ──────────────────────────────────────────────
    dynamic_plan_steps: list | None      # list[WorkflowStep] set by plan_sequential node
    dynamic_plan_high_risk: list         # list[int] — indices of steps requiring approval

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
