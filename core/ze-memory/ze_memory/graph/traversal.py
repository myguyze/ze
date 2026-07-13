"""Bounded graph traversal policy."""

from __future__ import annotations

from uuid import UUID

from ze_memory.graph.store import GraphStore
from ze_memory.graph.types import GraphExpansion


class BoundedExpansionPolicy:
    """Performs a bounded graph expansion from seed IDs via the graph store.

    max_hops and limit cap the traversal so it cannot become a runaway query.
    Callers should use max_hops=1 for latency-sensitive paths and increase only
    for explicit entity-centric recall queries.
    """

    def __init__(
        self,
        graph_store: GraphStore,
        max_hops: int = 1,
        limit: int = 20,
    ) -> None:
        self._store = graph_store
        self._max_hops = max_hops
        self._limit = limit

    async def expand(self, seed_ids: list[UUID]) -> GraphExpansion:
        if not seed_ids:
            return GraphExpansion()
        return await self._store.expand(
            seed_ids,
            max_hops=self._max_hops,
            limit=self._limit,
        )
