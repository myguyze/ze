from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze.routing.router import EmbeddingRouter

log = get_logger(__name__)


async def embed_route(state: AgentState, config: dict) -> dict:
    """Score the prompt against agent embeddings and produce a RoutingEnvelope."""
    router: EmbeddingRouter = config["configurable"]["router"]
    envelope = await router.route(
        prompt=state["prompt"],
        session_id=state["session_id"],
    )
    log.info(
        "orchestration_routed",
        session_id=state["session_id"],
        primary_agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        is_compound=envelope.is_compound,
    )
    return {"envelope": envelope}


async def decompose(state: AgentState, config: dict) -> dict:
    """
    For compound tasks the EmbeddingRouter already called haiku_fallback.decompose()
    internally. This node is a no-op passthrough that keeps the graph readable.
    The envelope already has all subtasks populated.
    """
    return {}
