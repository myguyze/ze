from __future__ import annotations

import time

from langchain_core.runnables import RunnableConfig
from ze_agents.types import GateDecision
from ze_agents.errors import WorkflowPlanError
from ze_agents.logging import get_logger
from ze_core.orchestration.state import AgentState
from ze_core.telemetry.context import set_agent_context

log = get_logger(__name__)

_HISTORY_HINT_TURNS = 4          # last N messages included as routing context
_HISTORY_HINT_CHARS = 240        # per-message truncation
_HISTORY_INACTIVITY_MINUTES = 30  # mirror fetch_context's session expiry default


def _history_hint(state: AgentState) -> str | None:
    """Compact tail of the conversation so anaphoric follow-ups
    ("are these recent?", "how did you get those?") route to the agent
    that produced the content being referenced."""
    messages = state.get("messages") or []
    if not messages:
        return None

    last_active = state.get("last_active_at")
    if last_active and (time.time() - last_active) > _HISTORY_INACTIVITY_MINUTES * 60:
        return None

    lines = []
    for msg in messages[-_HISTORY_HINT_TURNS:]:
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        lines.append(f"{msg.get('role', '?')}: {content[:_HISTORY_HINT_CHARS]}")
    if not lines:
        return None
    return "[Recent conversation]\n" + "\n".join(lines)


async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    from ze_core.routing.router import EmbeddingRouter

    router: EmbeddingRouter = config["configurable"]["router"]

    # preprocess has already set image_caption for image turns; use it for routing
    routing_text = state.get("image_caption") or state["prompt"]

    # Append after the message so the actual message content dominates the embedding
    history_hint = _history_hint(state)
    if history_hint:
        routing_text = f"{routing_text}\n\n{history_hint}"

    hints = state.get("routing_hints")
    if hints:
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
    from ze_agents.registry import get_enabled_agents
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
