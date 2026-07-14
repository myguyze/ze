from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from ze_agents.types import RetrievalRequest
from ze_memory.types import (
    Entity,
    Fact,
    MemoryContext,
    Procedure,
    ProfileFacet,
    Signal,
    SignalIngestResult,
    TaskState,
)


@runtime_checkable
class MemoryQueryable(Protocol):
    """Narrow interface that retrieval policies need from the store.

    Policies acquire a DB connection from `pool` and call `get_task_state`
    for task-scoped modules. Nothing else from the store is required.
    """

    @property
    def pool(self) -> Any: ...

    @property
    def settings(self) -> Any: ...

    @property
    def graph_store(self) -> Any: ...

    async def get_task_state(
        self,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> TaskState | None: ...


@runtime_checkable
class MemoryRetrievalPolicy(Protocol):
    async def retrieve(
        self, request: RetrievalRequest, store: MemoryQueryable
    ) -> MemoryContext: ...


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

    async def propose_events(self, events: list[Any]) -> None: ...

    async def propose_procedure(
        self,
        procedure: Procedure,
        linked_task_id: UUID | None = None,
        linked_task_type: str = "workflow",
    ) -> UUID | None: ...

    async def upsert_entity(self, entity: Entity) -> UUID: ...

    async def upsert_task_state(self, state: TaskState) -> None: ...

    async def get_task_state(
        self,
        task_id: UUID | None = None,
        goal_id: UUID | None = None,
    ) -> TaskState | None: ...

    async def get_profile(self) -> list[ProfileFacet]: ...

    async def upsert_profile_facets(self, facets: list[dict]) -> None: ...

    async def ingest_signal(self, signal: Signal) -> SignalIngestResult | None: ...
