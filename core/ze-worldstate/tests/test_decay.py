from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from ze_worldstate.decay import CONFIDENCE_FLOOR, cascade_from_evidence
from ze_worldstate.types import LoopClaimKind, LoopProvenance, LoopState, OpenLoop


def _loop(confidence=0.6) -> OpenLoop:
    return OpenLoop(
        id=uuid4(),
        title="Send Maria the contract",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=confidence,
        state=LoopState.SUSPECTED,
    )


async def test_sole_evidence_collapses_to_floor():
    loop = _loop()
    loop_store = AsyncMock()
    loop_store.list_by_evidence = AsyncMock(return_value=[loop])
    loop_store.count_evidence_links = AsyncMock(return_value=1)
    loop_store.set_confidence = AsyncMock()

    result = await cascade_from_evidence("fact", uuid4(), loop_store)

    assert result[0].confidence == CONFIDENCE_FLOOR
    loop_store.set_confidence.assert_awaited_once_with(loop.id, CONFIDENCE_FLOOR)


async def test_multi_evidence_loop_recomputes_from_remaining():
    loop = _loop(confidence=0.8)
    loop_store = AsyncMock()
    loop_store.list_by_evidence = AsyncMock(return_value=[loop])
    loop_store.count_evidence_links = AsyncMock(return_value=4)
    loop_store.set_confidence = AsyncMock()

    result = await cascade_from_evidence("episode", uuid4(), loop_store)

    expected = max(CONFIDENCE_FLOOR, 0.8 * 3 / 4)
    assert result[0].confidence == expected
    assert result[0].confidence < 0.8


async def test_floor_is_never_exactly_zero():
    loop = _loop(confidence=0.01)
    loop_store = AsyncMock()
    loop_store.list_by_evidence = AsyncMock(return_value=[loop])
    loop_store.count_evidence_links = AsyncMock(return_value=1)
    loop_store.set_confidence = AsyncMock()

    result = await cascade_from_evidence("fact", uuid4(), loop_store)

    assert result[0].confidence > 0.0
    assert result[0].confidence == CONFIDENCE_FLOOR


async def test_no_affected_loops_returns_empty():
    loop_store = AsyncMock()
    loop_store.list_by_evidence = AsyncMock(return_value=[])

    result = await cascade_from_evidence("fact", uuid4(), loop_store)
    assert result == []
