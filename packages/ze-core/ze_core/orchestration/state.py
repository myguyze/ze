from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict
from uuid import UUID

if TYPE_CHECKING:
    from ze_core.plugin import ZePlugin

from ze_core.capability.types import GateDecision
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.routing.types import RoutingEnvelope


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]   # "agent.intent" → mode string

    # ── Multimodal ─────────────────────────────────────────────────────────
    input_modality: str         # "text" | "voice" | "image" — default "text"
    audio_data: bytes | None    # raw audio bytes; cleared after preprocess transcribes them
    audio_mime: str | None      # e.g. "audio/ogg; codecs=opus"
    image_data: bytes | None    # raw image bytes; None for text/voice turns
    image_mime: str | None      # "image/jpeg" | "image/png" | None
    image_caption: str | None   # caption generated at preprocess; None until set

    # ── Routing ────────────────────────────────────────────────────────────
    envelope: RoutingEnvelope | None

    # ── Context ────────────────────────────────────────────────────────────
    memory_context: Any | None
    agent_context: AgentContext | None

    # ── Capability ─────────────────────────────────────────────────────────
    gate_decision: GateDecision | None

    # ── Execution ──────────────────────────────────────────────────────────
    agent_result: AgentResult | None
    subtask_results: list[AgentResult]
    pending_confirmation: bool

    # ── Conversation history ───────────────────────────────────────────────
    messages: list[dict]
    last_active_at: float | None

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
    components: list[dict]

    # ── Workflow execution (workflow_graph only) ────────────────────────────
    workflow_id: UUID | None
    workflow_execution_id: UUID | None
    workflow_steps: list | None          # list[WorkflowStep]
    current_step_index: int
    workflow_step_results: list          # list[StepResult]

    # ── Dynamic plan (plan_sequential node) ────────────────────────────────
    dynamic_plan_steps: list | None      # list[WorkflowStep]
    dynamic_plan_high_risk: list         # indices requiring approval

    # ── Routing context (populated by pre-route plugin nodes) ────────────────
    routing_hints: str | None            # injected by inject_goal_routing_context


def build_state_type(plugins: list[ZePlugin]) -> type:
    """Return a TypedDict class that merges AgentState with all plugin state extensions.

    Each plugin's state_extensions() should return a TypedDict subclass of AgentState
    (or of a previous extension). The merged class inherits from all extensions so its
    fields are accessible via the standard state["field"] syntax in graph nodes.

    Returns AgentState unchanged when no plugins contribute state extensions.
    """
    extensions = [p.state_extensions() for p in plugins if p.state_extensions() is not None]
    if not extensions:
        return AgentState
    # TypedDict supports multiple inheritance; Python resolves the metaclass from bases.
    # Each extension is expected to subclass AgentState (forming a diamond with AgentState
    # at the root), so the MRO is unambiguous.
    return type("ExtendedAgentState", tuple(extensions), {"__annotations__": {}})
