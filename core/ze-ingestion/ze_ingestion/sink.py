from __future__ import annotations

from typing import Any

from ze_agents.logging import get_logger

log = get_logger(__name__)


class MemorySink:
    """Pushes extracted facts into ze-memory."""

    def __init__(self, memory_store: Any) -> None:
        self._store = memory_store

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
