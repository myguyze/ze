# Phase 1 stub — full implementation in Phase 2 (spec: 03-memory.md)

import asyncpg

from ze.agents.types import AgentContext, AgentResult
from ze.logging import get_logger
from ze.memory.types import MemoryContext
from ze.settings import Settings


class MemoryStore:
    def __init__(self, pool: asyncpg.Pool, settings: Settings) -> None:
        self._pool = pool
        self._settings = settings
        self._log = get_logger(__name__)

    async def get_context(self, session_id: str, prompt: str) -> MemoryContext:
        """Return memory context for the given session. Phase 1: returns empty context."""
        return MemoryContext()

    async def write_episode(self, ctx: AgentContext, result: AgentResult) -> None:
        """Persist a completed interaction as an episode. Phase 1: no-op."""

    async def propose_facts(self, ctx: AgentContext, result: AgentResult) -> None:
        """Extract and propose new facts from the response. Phase 1: no-op."""
