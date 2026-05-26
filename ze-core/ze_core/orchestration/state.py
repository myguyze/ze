from __future__ import annotations

from typing import TypedDict

from ze_core.capability.types import GateDecision
from ze_core.memory.types import MemoryContext
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.routing.types import RoutingEnvelope


class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]   # "agent.intent" → mode string

    # ── Multimodal ─────────────────────────────────────────────────────────
    input_modality: str         # "text" | "voice" | "image" — default "text"
    image_data: bytes | None    # raw image bytes; None for text/voice turns
    image_mime: str | None      # "image/jpeg" | "image/png" | None
    image_caption: str | None   # caption generated at embed_route; None until set

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
    messages: list[dict]
    last_active_at: float | None

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
