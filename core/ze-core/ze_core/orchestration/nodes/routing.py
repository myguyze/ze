from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from ze_core.capability.types import GateDecision
from ze_core.errors import WorkflowPlanError
from ze_core.logging import get_logger
from ze_core.orchestration.state import AgentState
from ze_core.telemetry.context import set_agent_context

log = get_logger(__name__)


async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    from ze_core.routing.router import EmbeddingRouter

    router: EmbeddingRouter = config["configurable"]["router"]

    # preprocess has already set image_caption for image turns; use it for routing
    routing_text = state.get("image_caption") or state["prompt"]

    hints = state.get("routing_hints")
    if hints:
        # Append after the message so the actual message content dominates the embedding
        routing_text = f"{routing_text}\n\n{hints}"

    envelope = await router.route(prompt=routing_text, session_id=state["session_id"])
    log.info(
        "orchestration_routed",
        session_id=state["session_id"],
        primary_agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        is_compound=envelope.is_compound,
    )
    return {"envelope": envelope}


async def decompose(state: AgentState, config: RunnableConfig) -> dict:
    from ze_core.orchestration.registry import get_enabled_agents
    from ze_core.routing import fallback
    from ze_core.routing.router import EmbeddingRouter

    client = config["configurable"]["openrouter_client"]
    router: EmbeddingRouter | None = config["configurable"].get("router")

    fallback_model = "anthropic/claude-haiku-4-5"
    if router is not None:
        fallback_model = router._config.fallback_model

    envelope = state.get("envelope")
    raw_scores: dict = envelope.raw_scores if envelope else {}

    new_envelope = await fallback.decompose(
        prompt=state["prompt"],
        raw_scores=raw_scores,
        client=client,
        agent_registry=get_enabled_agents(),
        fallback_model=fallback_model,
        logger=log,
    )

    # Patch per-subtask model using complexity estimation when router is available.
    if router is not None and new_envelope.subtasks:
        primary_intent = new_envelope.subtasks[0].intent
        complexity = router._estimator.classify(state["prompt"], primary_intent, new_envelope.confidence)
        for subtask in new_envelope.subtasks:
            subtask.model = router._resolve_model(subtask.agent, complexity)
        new_envelope.complexity = complexity

    log.info(
        "orchestration_decomposed",
        session_id=state["session_id"],
        subtask_count=len(new_envelope.subtasks),
        is_sequential=new_envelope.is_sequential,
    )
    return {"envelope": new_envelope}


async def plan_sequential(state: AgentState, config: RunnableConfig) -> dict:
    """Call WorkflowPlanner to produce an ordered step list, then pre-check each step
    against the capability gate to identify any steps requiring user approval."""
    from ze_core.capability.gate import CapabilityGate

    planner = config["configurable"]["workflow_planner"]
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
