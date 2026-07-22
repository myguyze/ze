from __future__ import annotations

from typing import Any

from ze_logging import get_logger

from ze_worldstate.extraction import propose_loop_candidates
from ze_worldstate.types import EvidenceRef

log = get_logger(__name__)


async def _propose(
    text: str,
    provenance: str,
    configurable: dict,
    evidence_refs: list[EvidenceRef] | None = None,
) -> None:
    loop_store = configurable.get("loop_store")
    if loop_store is None or not text or not text.strip():
        return
    try:
        await propose_loop_candidates(
            text=text,
            provenance=provenance,
            evidence_refs=evidence_refs or [],
            llm_client=configurable["openrouter_client"],
            embedder=configurable["embedder"],
            loop_store=loop_store,
            entity_resolver=configurable.get("loop_entity_resolver"),
            graph_store=configurable.get("loop_graph_store"),
        )
    except Exception as exc:
        log.warning("loop_extraction_failed", provenance=provenance, error=str(exc))


async def conversation_memory_hook(result: Any, ctx: Any, config: dict) -> None:
    """FR-008's conversation inflow — invoked via the `write_memory` node's
    generic `memory_hooks` extension point (FR-017's direct-write proto-contribution).
    """
    await _propose(ctx.prompt, "conversation", config["configurable"])


def make_loop_extractor_from_parts(
    *,
    loop_store: Any,
    loop_graph_store: Any,
    loop_entity_resolver: Any,
    openrouter_client: Any,
    embedder: Any,
):
    """Builds a plain `(text, provenance) -> None` async callable, for wiring into
    inflow modules (ze-messenger, ze-calendar, ze-ingestion) that must not import
    `ze_worldstate` directly (plan.md: ze-api is the only wiring point for FR-017's
    direct-write proto-contribution).
    """
    configurable = {
        "loop_store": loop_store,
        "loop_graph_store": loop_graph_store,
        "loop_entity_resolver": loop_entity_resolver,
        "openrouter_client": openrouter_client,
        "embedder": embedder,
    }

    async def _extractor(text: str, provenance: str) -> None:
        await _propose(text, provenance, configurable)

    return _extractor


def make_loop_extractor(container: Any):
    """Same as `make_loop_extractor_from_parts`, sourced from a built `ZeContainer`."""
    return make_loop_extractor_from_parts(
        loop_store=container.loop_store,
        loop_graph_store=container.loop_graph_store,
        loop_entity_resolver=container.loop_entity_resolver,
        openrouter_client=container.openrouter_client,
        embedder=container.embedder,
    )
