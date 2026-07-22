from __future__ import annotations

from uuid import UUID

from ze_logging import get_logger

from ze_worldstate.store import LoopStore
from ze_worldstate.types import OpenLoop

log = get_logger(__name__)

# A dropped-to-floor loop still exists for the user to see why it faded
# (Edge Cases) — never exactly 0.0 (research.md §4).
CONFIDENCE_FLOOR = 0.05


async def cascade_from_evidence(
    evidence_type: str,
    evidence_id: UUID,
    loop_store: LoopStore,
) -> list[OpenLoop]:
    """Called synchronously by the evidence-writing code path (research.md §3).

    Multiplicative/weighted-average decay: a loop whose sole evidence was just
    contradicted/expired/retracted collapses to the confidence floor; a loop
    with multiple evidence links is recomputed from the remaining (non-retracted)
    evidence weight (SC-006).
    """
    affected = await loop_store.list_by_evidence(evidence_type, evidence_id)
    updated: list[OpenLoop] = []
    for loop in affected:
        total_evidence = await loop_store.count_evidence_links(loop.id)
        if total_evidence <= 1:
            new_confidence = CONFIDENCE_FLOOR
        else:
            remaining = total_evidence - 1
            new_confidence = max(
                CONFIDENCE_FLOOR, loop.confidence * remaining / total_evidence
            )
        await loop_store.set_confidence(loop.id, new_confidence)
        loop.confidence = new_confidence
        updated.append(loop)
        log.info(
            "open_loop_confidence_decayed",
            loop_id=str(loop.id),
            new_confidence=new_confidence,
            evidence_type=evidence_type,
            evidence_id=str(evidence_id),
        )
    return updated
