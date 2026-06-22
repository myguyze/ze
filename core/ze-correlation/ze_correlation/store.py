from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from ze_logging import get_logger

from ze_correlation.types import EvidenceRef, Hypothesis

log = get_logger(__name__)

UTC = timezone.utc


class PostgresHypothesisStore:
    def __init__(self, pool: object) -> None:
        self._pool = pool

    async def save(self, hypothesis: Hypothesis) -> None:
        evidence_data = [
            {
                "kind": e.kind,
                "id": str(e.id),
                "label": e.label,
                "external_ref": e.external_ref,
                "origin": e.origin,
                "retrieved_at": e.retrieved_at.isoformat(),
                "ingested_at": e.ingested_at.isoformat() if e.ingested_at else None,
            }
            for e in hypothesis.evidence
        ]
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                """
                INSERT INTO correlation_hypothesis
                  (id, summary, narrative, relation, confidence, relevance,
                   evidence, entities, surfaced, feedback, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11)
                ON CONFLICT (id) DO NOTHING
                """,
                hypothesis.id,
                hypothesis.summary,
                hypothesis.narrative,
                hypothesis.relation,
                hypothesis.confidence,
                hypothesis.relevance,
                json.dumps(evidence_data),
                json.dumps([str(e) for e in hypothesis.entities]),
                hypothesis.surfaced,
                hypothesis.feedback,
                hypothesis.created_at,
            )
        log.info("hypothesis_saved", hypothesis_id=str(hypothesis.id))

    async def get(self, hypothesis_id: UUID) -> Hypothesis | None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            row = await conn.fetchrow(
                "SELECT * FROM correlation_hypothesis WHERE id = $1",
                hypothesis_id,
            )
        if row is None:
            return None
        return _row_to_hypothesis(row)

    async def list_unsurfaced(self, limit: int = 20) -> list[Hypothesis]:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch(
                "SELECT * FROM correlation_hypothesis WHERE surfaced = false"
                " ORDER BY created_at DESC LIMIT $1",
                limit,
            )
        return [_row_to_hypothesis(r) for r in rows]

    async def mark_surfaced(self, hypothesis_id: UUID) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "UPDATE correlation_hypothesis SET surfaced = true WHERE id = $1",
                hypothesis_id,
            )

    async def list_recently_surfaced_summaries(self, hours: float) -> list[str]:
        """Return summaries of hypotheses pushed in the last *hours* hours."""
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            rows = await conn.fetch(
                "SELECT summary FROM correlation_hypothesis"
                " WHERE surfaced = true"
                " AND created_at > NOW() - ($1 * INTERVAL '1 hour')",
                hours,
            )
        return [r["summary"] for r in rows]

    async def set_feedback(
        self,
        hypothesis_id: UUID,
        feedback: str,
    ) -> None:
        async with self._pool.acquire() as conn:  # type: ignore[union-attr]
            await conn.execute(
                "UPDATE correlation_hypothesis SET feedback = $1 WHERE id = $2",
                feedback,
                hypothesis_id,
            )


def _row_to_hypothesis(row: object) -> Hypothesis:
    evidence_raw = json.loads(row["evidence"])  # type: ignore[index]
    evidence = [
        EvidenceRef(
            kind=e["kind"],
            id=UUID(e["id"]),
            label=e["label"],
            external_ref=e.get("external_ref"),
            origin=e["origin"],
            retrieved_at=datetime.fromisoformat(e["retrieved_at"]),
            ingested_at=datetime.fromisoformat(e["ingested_at"]) if e.get("ingested_at") else None,
        )
        for e in evidence_raw
    ]
    entities_raw = json.loads(row["entities"])  # type: ignore[index]
    return Hypothesis(
        id=row["id"],  # type: ignore[index]
        summary=row["summary"],  # type: ignore[index]
        narrative=row["narrative"],  # type: ignore[index]
        relation=row["relation"],  # type: ignore[index]
        confidence=row["confidence"],  # type: ignore[index]
        relevance=row["relevance"],  # type: ignore[index]
        evidence=evidence,
        entities=[UUID(e) for e in entities_raw],
        created_at=row["created_at"],  # type: ignore[index]
        surfaced=row["surfaced"],  # type: ignore[index]
        feedback=row["feedback"],  # type: ignore[index]
    )
