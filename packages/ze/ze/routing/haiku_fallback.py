"""Ze routing fallback — ze-core implementation with optional settings adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ze_core.orchestration.registry import get_enabled_agents
from ze_core.routing import fallback
from ze_core.routing.types import RouterConfig, RoutingEnvelope

if TYPE_CHECKING:
    import structlog

    from ze.openrouter.client import OpenRouterClient
    from ze.settings import Settings

_extract_json_object = fallback._extract_json_object


async def decompose(
    prompt: str,
    raw_scores: dict[str, float],
    client: OpenRouterClient,
    settings: Settings,
    logger: structlog.BoundLogger | None = None,
) -> RoutingEnvelope:
    """Ask the router fallback model to decompose a prompt (tests / legacy callers)."""
    cfg = RouterConfig()
    routing_cfg = settings.routing_config
    if routing_cfg.get("fallback_model"):
        cfg = RouterConfig(fallback_model=str(routing_cfg["fallback_model"]))

    return await fallback.decompose(
        prompt=prompt,
        raw_scores=raw_scores,
        client=client,
        agent_registry=get_enabled_agents(),
        fallback_model=cfg.fallback_model,
        logger=logger,
    )


__all__ = ["_extract_json_object", "decompose"]
