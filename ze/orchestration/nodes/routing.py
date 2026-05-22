import base64

from langchain_core.runnables import RunnableConfig

from ze.capability.gate import CapabilityGate
from ze.capability.types import GateDecision
from ze.errors import WorkflowPlanError
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.orchestration.state import AgentState
from ze.routing.router import EmbeddingRouter
from ze.settings import Settings
from ze.telemetry.context import set_agent_context
from ze.workflow.planner import WorkflowPlanner

log = get_logger(__name__)


async def _vision_caption(
    image_data: bytes,
    image_mime: str,
    client: OpenRouterClient,
    model: str,
) -> str:
    """Call a cheap vision model for a one-sentence routing description."""
    message = {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image_mime};base64,{base64.b64encode(image_data).decode()}",
                    "detail": "low",
                },
            },
            {"type": "text", "text": "Describe this image in one sentence for intent classification."},
        ],
    }
    return await client.complete(messages=[message], model=model, max_tokens=80)


async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    """Score the prompt against agent embeddings and produce a RoutingEnvelope."""
    router: EmbeddingRouter = config["configurable"]["router"]
    updates: dict = {}

    routing_text = state["prompt"]

    if state.get("input_modality") == "image":
        if not state.get("prompt"):
            client: OpenRouterClient = config["configurable"]["openrouter_client"]
            settings: Settings = config["configurable"]["settings"]
            caption_model = settings.config.get("models", {}).get(
                "vision_caption", "google/gemini-flash-1.5"
            )
            caption = await _vision_caption(
                state["image_data"], state["image_mime"], client, caption_model
            )
            routing_text = caption
            updates["image_caption"] = caption
        else:
            updates["image_caption"] = state["prompt"]

    envelope = await router.route(
        prompt=routing_text,
        session_id=state["session_id"],
    )
    log.info(
        "orchestration_routed",
        session_id=state["session_id"],
        primary_agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        is_compound=envelope.is_compound,
        is_sequential=envelope.is_sequential,
    )
    updates["envelope"] = envelope
    return updates


async def decompose(state: AgentState, config: RunnableConfig) -> dict:
    """
    For compound tasks the EmbeddingRouter already called haiku_fallback.decompose()
    internally. This node is a no-op passthrough that keeps the graph readable.
    The envelope already has all subtasks populated.
    """
    return {}


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
