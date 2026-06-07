from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ze_core.memory.types import Episode, MemoryContext, UserFact, UserProfile


@runtime_checkable
class MemoryStore(Protocol):
    async def get_context(
        self,
        prompt_embedding: Any,
        agent: str,
        token_budget: dict[str, int] | None = None,
    ) -> MemoryContext: ...

    async def write_episode(
        self,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None: ...

    async def propose_facts(self, proposals: list[UserFact]) -> None: ...

    async def get_profile(self) -> UserProfile | None: ...

    async def list_recent_facts(self, days: int, limit: int) -> list[UserFact]: ...

    async def list_recent_episodes(self, days: int, limit: int) -> list[Episode]: ...
