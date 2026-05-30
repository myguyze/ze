from langchain_core.runnables import RunnableConfig

from ze_core.capability.gate import CapabilityGate
from ze_core.capability.types import GateDecision
from ze_core.errors import WorkflowPlanError
from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze_core.routing.router import EmbeddingRouter
from ze_core.telemetry.context import set_agent_context
from ze_core.workflow.planner import WorkflowPlanner
from ze_core.orchestration.nodes.routing import decompose as zc_decompose

log = get_logger(__name__)


async def decompose(state: AgentState, config: RunnableConfig) -> dict:
    """LLM decomposition when embedding confidence is low (ze-core fallback)."""
    result = await zc_decompose(state, config)
    envelope = result.get("envelope")
    if not envelope or not envelope.subtasks:
        return result

    router: EmbeddingRouter | None = config["configurable"].get("router")
    if router is None:
        return result

    prompt = state["prompt"]
    primary_intent = envelope.subtasks[0].intent
    complexity = router._estimator.classify(prompt, primary_intent, envelope.confidence)
    for subtask in envelope.subtasks:
        subtask.model = router._resolve_model(subtask.agent, complexity)
    envelope.complexity = complexity
    return result


async def plan_sequential(state: AgentState, config: RunnableConfig) -> dict:
    """
    For sequential compound tasks: call WorkflowPlanner to produce an ordered step
    list, then pre-check each step against the capability gate to identify any steps
    that require user approval before execution.
    """
    planner: WorkflowPlanner = config["configurable"]["workflow_planner"]
    gate: CapabilityGate = config["configurable"]["capability_gate"]
    session_overrides: dict = state.get("session_overrides") or {}

    set_agent_context("workflow_planner")
    try:
        steps = await planner.plan(state["prompt"])
    except WorkflowPlanError as exc:
        log.warning("plan_sequential_failed", error=str(exc))
        return {
            "final_response": f"I couldn't plan that as a workflow: {exc}",
            "dynamic_plan_steps": None,
            "dynamic_plan_high_risk": [],
        }

    high_risk: list[int] = []
    for i, step in enumerate(steps):
        agent = step.agent_hint or "research"
        decision = gate.evaluate(agent, step.intent, session_overrides)
        if decision in (GateDecision.AWAIT_CONFIRMATION, GateDecision.DRAFT, GateDecision.BLOCKED):
            high_risk.append(i)

    log.info("plan_sequential_ready", steps=len(steps), high_risk=high_risk)
    return {
        "dynamic_plan_steps": steps,
        "dynamic_plan_high_risk": high_risk,
    }
