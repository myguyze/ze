from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ze_memory.types import (
    Fact,
    MemoryContext,
    ProfileFacet,
    RetrievalRequest,
    TaskState,
)


@runtime_checkable
class MemoryRetrievalPolicy(Protocol):
    async def retrieve(self, request: RetrievalRequest, store: Any) -> MemoryContext: ...


@runtime_checkable
class MemoryPolicyRegistry(Protocol):
    def for_module(self, module: str) -> MemoryRetrievalPolicy: ...


@runtime_checkable
class MemoryStore(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> MemoryContext: ...

    async def write_episode(
        self,
        session_id: str,
        agent: str,
        prompt: str,
        response: str,
        embedding: Any,
    ) -> None: ...

    async def propose_facts(self, proposals: list[Fact]) -> None: ...

    async def upsert_task_state(self, state: TaskState) -> None: ...

    async def get_task_state(
        self,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> TaskState | None: ...

    async def get_profile(self) -> list[ProfileFacet]: ...
