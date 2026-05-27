"""Ze memory consolidation — ze-core implementation with telemetry hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ze_core.memory.consolidator import MemoryConsolidator as _CoreMemoryConsolidator
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.memory.types import ConsolidationReport
from ze.telemetry.context import set_agent_context, set_flow_context

if TYPE_CHECKING:
    from ze.openrouter.client import OpenRouterClient
    from ze.settings import Settings


class MemoryConsolidator:
    """Wraps ze-core consolidator; accepts pool for Container wiring compatibility."""

    def __init__(
        self,
        pool: Any,
        embedder: Any,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._store = PostgresMemoryStore(
            pool=pool,
            embedder=embedder,
            openrouter_client=openrouter_client,
            settings=settings,
        )
        self._inner = _CoreMemoryConsolidator(
            store=self._store,
            embedder=embedder,
            openrouter_client=openrouter_client,
            settings=settings,
        )

    async def run(self) -> ConsolidationReport:
        set_flow_context("memory_consolidation")
        set_agent_context("memory_consolidation")
        return await self._inner.run()

    async def dedup_facts(self) -> int:
        return await self._inner.dedup_facts()

    async def expire_facts(self) -> tuple[int, int]:
        return await self._inner.expire_facts()

    async def archive_episodes(self) -> tuple[int, int]:
        return await self._inner.archive_episodes()

    async def synthesise_profile(self) -> bool:
        return await self._inner.update_profile()

    async def update_profile(self) -> bool:
        return await self._inner.update_profile()
