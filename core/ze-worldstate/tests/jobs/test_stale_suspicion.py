from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from ze_worldstate.jobs.stale_suspicion import StaleSuspicionJob
from ze_worldstate.types import LoopClaimKind, LoopProvenance, LoopState, OpenLoop


def _loop(age_days: int, state=LoopState.SUSPECTED) -> OpenLoop:
    return OpenLoop(
        id=uuid4(),
        title="Some loop",
        claim_kind=LoopClaimKind.SUSPICION,
        provenance=LoopProvenance.CONVERSATION,
        confidence=0.3,
        state=state,
        created_at=datetime.now(timezone.utc) - timedelta(days=age_days),
    )


async def test_suspected_loop_older_than_window_is_dropped():
    old_loop = _loop(age_days=20)
    loop_store = AsyncMock()
    loop_store.list = AsyncMock(return_value=[old_loop])
    loop_store.transition = AsyncMock()

    job = StaleSuspicionJob(loop_store=loop_store, window_days=14)
    await job.run()

    loop_store.transition.assert_awaited_once_with(old_loop.id, LoopState.DROPPED.value)


async def test_suspected_loop_within_window_is_untouched():
    fresh_loop = _loop(age_days=2)
    loop_store = AsyncMock()
    loop_store.list = AsyncMock(return_value=[fresh_loop])
    loop_store.transition = AsyncMock()

    job = StaleSuspicionJob(loop_store=loop_store, window_days=14)
    await job.run()

    loop_store.transition.assert_not_awaited()


async def test_only_suspected_loops_are_swept():
    loop_store = AsyncMock()
    loop_store.list = AsyncMock(return_value=[])
    loop_store.transition = AsyncMock()

    job = StaleSuspicionJob(loop_store=loop_store, window_days=14)
    await job.run()

    loop_store.list.assert_awaited_once_with([LoopState.SUSPECTED.value])
    loop_store.transition.assert_not_awaited()
