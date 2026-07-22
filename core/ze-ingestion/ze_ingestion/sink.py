from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from ze_logging import get_logger

log = get_logger(__name__)


class MemorySink:
    """Pushes extracted facts into ze-memory."""

    def __init__(
        self,
        memory_store: Any,
        loop_extractor: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._store = memory_store
        # Optional hook wired post-construction by ze-api (open-loop extraction,
        # FR-008's ingestion inflow) — kept generic here so ze-ingestion has no
        # dependency on ze-worldstate (plan.md: ze-api is the only wiring point).
        self.loop_extractor = loop_extractor

    async def push(self, ingestion_id: str, facts: list[str]) -> None:
        if not facts:
            return
        from ze_memory.types import Fact

        proposals = [Fact(predicate=f, value=f) for f in facts]
        try:
            await self._store.propose_facts(proposals)
            log.info("memory_sink_pushed", ingestion_id=ingestion_id, count=len(facts))
        except Exception as exc:
            log.warning("memory_sink_failed", ingestion_id=ingestion_id, error=str(exc))

        if self.loop_extractor is not None:
            try:
                await self.loop_extractor(". ".join(facts), "ingestion")
            except Exception as exc:
                log.warning(
                    "ingestion_loop_extraction_failed",
                    ingestion_id=ingestion_id,
                    error=str(exc),
                )
