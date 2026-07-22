from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from ze_worldstate import review
from ze_worldstate.types import (
    EvidenceRef,
    LoopClaimKind,
    LoopProvenance,
    LoopState,
    OpenLoop,
)


def _loop(state=LoopState.SUSPECTED) -> OpenLoop:
    return OpenLoop(
        id=uuid4(),
        title="Renew passport",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=0.3,
        state=state,
    )


async def test_confirm_loop_transitions_suspected_to_active():
    loop_store = AsyncMock()
    active_loop = _loop(state=LoopState.ACTIVE)
    loop_store.transition = AsyncMock(return_value=active_loop)

    result = await review.confirm_loop(loop_store, uuid4())
    loop_store.transition.assert_awaited_once()
    assert result.state == LoopState.ACTIVE


async def test_close_loop_transitions_to_closed():
    loop_store = AsyncMock()
    closed_loop = _loop(state=LoopState.CLOSED)
    loop_store.transition = AsyncMock(return_value=closed_loop)

    result = await review.close_loop(loop_store, uuid4())
    assert result.state == LoopState.CLOSED


async def test_drop_loop_computes_and_persists_fingerprint():
    loop_id = uuid4()
    loop_store = AsyncMock()
    refs = [EvidenceRef(evidence_type="episode", evidence_id=uuid4())]
    loop_store.list_evidence = AsyncMock(return_value=refs)
    dropped_loop = _loop(state=LoopState.DROPPED)
    loop_store.transition = AsyncMock(return_value=dropped_loop)
    loop_store.set_dismissed_evidence_fingerprint = AsyncMock()

    result = await review.drop_loop(loop_store, loop_id)

    loop_store.set_dismissed_evidence_fingerprint.assert_awaited_once()
    assert result.dismissed_evidence_fingerprint is not None
    assert result.state == LoopState.DROPPED


async def test_drop_loop_never_deletes_evidence_or_entities():
    """FR-013: drop only changes open_loops.state / dismissed_evidence_fingerprint,
    never memory_entities/memory_facts/memory_episodes or the loop's own links."""
    loop_id = uuid4()
    loop_store = AsyncMock()
    loop_store.list_evidence = AsyncMock(return_value=[])
    loop_store.transition = AsyncMock(return_value=_loop(state=LoopState.DROPPED))
    loop_store.set_dismissed_evidence_fingerprint = AsyncMock()

    await review.drop_loop(loop_store, loop_id)

    loop_store.transition.assert_awaited_once_with(loop_id, LoopState.DROPPED.value)
    loop_store.list_evidence.assert_awaited_once()
    loop_store.set_dismissed_evidence_fingerprint.assert_awaited_once()
