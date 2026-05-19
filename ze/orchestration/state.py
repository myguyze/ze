import operator
from typing import Annotated, TypedDict
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

    # ── Routing ────────────────────────────────────────────────────────────
    envelope: RoutingEnvelope | None

    # ── Context ────────────────────────────────────────────────────────────
    memory_context: MemoryContext | None
    agent_context: AgentContext | None

    # ── Capability ─────────────────────────────────────────────────────────
    gate_decision: GateDecision | None

    # ── Execution ──────────────────────────────────────────────────────────
    agent_result: AgentResult | None
    # Annotated with operator.add so compound subtask branches can accumulate results
    subtask_results: Annotated[list[AgentResult], operator.add]
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

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
