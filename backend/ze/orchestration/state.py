import operator
from typing import Annotated, TypedDict

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

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
