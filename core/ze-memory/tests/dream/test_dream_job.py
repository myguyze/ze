"""Tests for dream/job.py — DreamJob (78a + 78b)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_memory.dream.job import DreamJob


def _make_job(timeout: int = 60, with_client: bool = False):
    dream_store = AsyncMock()
    dream_store.create_run = AsyncMock(return_value=uuid4())
    dream_store.finish_run = AsyncMock()
    dream_store.write_journal_entry = AsyncMock()
    dream_store.get_pending_artifacts_for_run = AsyncMock(return_value=[])

    client = AsyncMock() if with_client else None

    job = DreamJob(
        pool=MagicMock(),
        embedder=MagicMock(),
        consolidator=MagicMock(),
        dream_store=dream_store,
        client=client,
        settings={"dream": {"job_timeout_seconds": timeout}},
    )
    return job, dream_store, client


async def test_run_completes_and_writes_journal():
    job, dream_store, client = _make_job(with_client=True)
    with (
        patch.object(
            job._sleep_pass,
            "run",
            new=AsyncMock(return_value={"episodes_scored": 3, "episodes_replayed": 1, "duration_ms": 10}),
        ),
        patch.object(
            job._dream_pass,
            "run",
            new=AsyncMock(return_value={"artifacts_scored": 0, "policies": 0, "stress_tests": 0, "duration_ms": 5}),
        ),
        patch.object(
            job._promoter,
            "run_morning_integration",
            new=AsyncMock(return_value={"promoted": 0, "needs_review": 0, "rejected": 0, "duration_ms": 5}),
        ),
        patch.object(
            job._journal,
            "write_entry",
            new=AsyncMock(return_value=uuid4()),
        ) as mock_journal,
        patch(
            "ze_memory.dream.job.expire_retrieval_cache",
            new=AsyncMock(return_value=0),
        ) as mock_expire,
    ):
        await job.run()
    dream_store.finish_run.assert_awaited_once()
    mock_journal.assert_awaited_once()
    mock_expire.assert_awaited_once_with(job._pool)


async def test_run_without_client_skips_dream_pass_and_journal():
    """Without a client, dream pass and journal are skipped gracefully."""
    job, dream_store, _ = _make_job(with_client=False)
    with (
        patch.object(
            job._sleep_pass,
            "run",
            new=AsyncMock(return_value={"episodes_scored": 3, "episodes_replayed": 1, "duration_ms": 10}),
        ),
        patch.object(
            job._promoter,
            "run_morning_integration",
            new=AsyncMock(return_value={"promoted": 0, "needs_review": 0, "rejected": 0, "duration_ms": 5}),
        ),
        patch(
            "ze_memory.dream.job.expire_retrieval_cache",
            new=AsyncMock(return_value=0),
        ),
    ):
        await job.run()
    dream_store.finish_run.assert_awaited_once()
    dream_store.write_journal_entry.assert_not_awaited()


async def test_run_records_timeout_error():
    job, dream_store, _ = _make_job()
    with (
        patch(
            "ze_memory.dream.job.asyncio.wait_for",
            new=AsyncMock(side_effect=asyncio.TimeoutError()),
        ),
        patch(
            "ze_memory.dream.job.expire_retrieval_cache",
            new=AsyncMock(return_value=2),
        ) as mock_expire,
    ):
        await job.run()

    finish_kwargs = dream_store.finish_run.call_args.kwargs
    assert finish_kwargs["error"] is not None
    assert "timed out" in finish_kwargs["error"]
    dream_store.write_journal_entry.assert_not_awaited()
    mock_expire.assert_awaited_once_with(job._pool)
