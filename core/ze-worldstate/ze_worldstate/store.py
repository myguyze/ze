from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from ze_logging import get_logger
from ze_sdk import DBPool

from ze_worldstate.errors import InvalidLoopTransitionError, LoopNotFoundError
from ze_worldstate.types import (
    EvidenceRef,
    LoopClaimKind,
    LoopProvenance,
    LoopState,
    OpenLoop,
)

log = get_logger(__name__)

# Phase A transition matrix — active -> drifting is Phase B (automatic detection),
# not producible here even though `drifting` must exist as a valid target state.
_ALLOWED_TRANSITIONS: dict[LoopState, set[LoopState]] = {
    LoopState.SUSPECTED: {LoopState.ACTIVE, LoopState.DROPPED},
    LoopState.ACTIVE: {LoopState.CLOSED, LoopState.DROPPED},
    LoopState.DRIFTING: {LoopState.CLOSED, LoopState.DROPPED},
    LoopState.CLOSED: set(),
    LoopState.DROPPED: set(),
}


def _loop_from_row(row) -> OpenLoop:
    return OpenLoop(
        id=row["id"],
        title=row["title"],
        state=LoopState(row["state"]),
        claim_kind=LoopClaimKind(row["claim_kind"]),
        provenance=LoopProvenance(row["provenance"]),
        confidence=row["confidence"],
        goal_id=row["goal_id"],
        dismissed_evidence_fingerprint=row["dismissed_evidence_fingerprint"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        confirmed_at=row["confirmed_at"],
        closed_at=row["closed_at"],
    )


class LoopStore(Protocol):
    async def create(self, loop: OpenLoop) -> OpenLoop: ...

    async def get(self, loop_id: UUID) -> OpenLoop | None: ...

    async def list(self, states: list[str] | None = None) -> list[OpenLoop]: ...

    async def transition(self, loop_id: UUID, new_state: str) -> OpenLoop: ...

    async def link_entity(self, loop_id: UUID, entity_id: UUID) -> None: ...

    async def link_evidence(
        self, loop_id: UUID, evidence_type: str, evidence_id: UUID
    ) -> None: ...

    async def set_confidence(self, loop_id: UUID, confidence: float) -> None: ...

    async def set_dismissed_evidence_fingerprint(
        self, loop_id: UUID, fingerprint: str
    ) -> None: ...

    async def list_by_evidence(
        self, evidence_type: str, evidence_id: UUID
    ) -> list[OpenLoop]: ...

    async def count_evidence_links(self, loop_id: UUID) -> int: ...

    async def list_evidence(self, loop_id: UUID) -> list[EvidenceRef]: ...


class PostgresLoopStore:
    def __init__(self, pool: DBPool) -> None:
        self._pool = pool

    async def create(self, loop: OpenLoop) -> OpenLoop:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO open_loops
                  (title, state, claim_kind, provenance, confidence, goal_id,
                   dismissed_evidence_fingerprint, confirmed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING *
                """,
                loop.title,
                loop.state.value,
                loop.claim_kind.value,
                loop.provenance.value,
                loop.confidence,
                loop.goal_id,
                loop.dismissed_evidence_fingerprint,
                loop.confirmed_at,
            )
        result = _loop_from_row(row)
        log.info(
            "open_loop_created",
            loop_id=str(result.id),
            state=result.state.value,
            provenance=result.provenance.value,
        )
        return result

    async def get(self, loop_id: UUID) -> OpenLoop | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM open_loops WHERE id = $1", loop_id)
        return _loop_from_row(row) if row else None

    async def list(self, states: list[str] | None = None) -> list[OpenLoop]:
        async with self._pool.acquire() as conn:
            if states:
                rows = await conn.fetch(
                    "SELECT * FROM open_loops WHERE state = ANY($1)"
                    " ORDER BY created_at DESC",
                    states,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM open_loops ORDER BY created_at DESC"
                )
        return [_loop_from_row(r) for r in rows]

    async def transition(self, loop_id: UUID, new_state: str) -> OpenLoop:
        target = LoopState(new_state)
        loop = await self.get(loop_id)
        if loop is None:
            raise LoopNotFoundError(f"Loop {loop_id} not found")

        allowed = _ALLOWED_TRANSITIONS.get(loop.state, set())
        if target not in allowed:
            raise InvalidLoopTransitionError(
                f"Cannot transition loop {loop_id} from {loop.state.value} to {target.value}"
            )

        now = datetime.now(timezone.utc)
        confirmed_at = loop.confirmed_at
        closed_at = loop.closed_at
        if target == LoopState.ACTIVE:
            confirmed_at = now
        if target in (LoopState.CLOSED, LoopState.DROPPED):
            closed_at = now

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE open_loops
                SET state = $2, confirmed_at = $3, closed_at = $4, updated_at = now()
                WHERE id = $1
                RETURNING *
                """,
                loop_id,
                target.value,
                confirmed_at,
                closed_at,
            )
        result = _loop_from_row(row)
        log.info(
            "open_loop_transitioned",
            loop_id=str(loop_id),
            from_state=loop.state.value,
            to_state=target.value,
        )
        return result

    async def link_entity(self, loop_id: UUID, entity_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_relationships
                  (source_id, source_type, predicate, target_id, target_type,
                   confidence, creation_method)
                VALUES ($1, 'entity', 'has_open_loop', $2, 'open_loop', 1.0, 'extracted')
                ON CONFLICT (source_id, predicate, target_id) WHERE target_id IS NOT NULL
                DO NOTHING
                """,
                entity_id,
                loop_id,
            )

    async def link_evidence(
        self, loop_id: UUID, evidence_type: str, evidence_id: UUID
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_relationships
                  (source_id, source_type, predicate, target_id, target_type,
                   confidence, creation_method)
                VALUES ($1, 'open_loop', 'derived_from', $2, $3, 1.0, 'extracted')
                ON CONFLICT (source_id, predicate, target_id) WHERE target_id IS NOT NULL
                DO NOTHING
                """,
                loop_id,
                evidence_id,
                evidence_type,
            )

    async def set_confidence(self, loop_id: UUID, confidence: float) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE open_loops SET confidence = $2, updated_at = now() WHERE id = $1",
                loop_id,
                confidence,
            )

    async def set_dismissed_evidence_fingerprint(
        self, loop_id: UUID, fingerprint: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE open_loops SET dismissed_evidence_fingerprint = $2,"
                " updated_at = now() WHERE id = $1",
                loop_id,
                fingerprint,
            )

    async def list_by_evidence(
        self, evidence_type: str, evidence_id: UUID
    ) -> list[OpenLoop]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT ol.*
                FROM open_loops ol
                JOIN memory_relationships mr
                  ON mr.source_id = ol.id
                WHERE mr.source_type = 'open_loop'
                  AND mr.predicate = 'derived_from'
                  AND mr.target_type = $1
                  AND mr.target_id = $2
                """,
                evidence_type,
                evidence_id,
            )
        return [_loop_from_row(r) for r in rows]

    async def count_evidence_links(self, loop_id: UUID) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT COUNT(*) AS n
                FROM memory_relationships
                WHERE source_id = $1 AND source_type = 'open_loop'
                  AND predicate = 'derived_from'
                """,
                loop_id,
            )
        return row["n"] if row else 0

    async def list_evidence(self, loop_id: UUID) -> list[EvidenceRef]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT target_type, target_id
                FROM memory_relationships
                WHERE source_id = $1 AND source_type = 'open_loop'
                  AND predicate = 'derived_from'
                """,
                loop_id,
            )
        return [
            EvidenceRef(evidence_type=r["target_type"], evidence_id=r["target_id"])
            for r in rows
        ]
