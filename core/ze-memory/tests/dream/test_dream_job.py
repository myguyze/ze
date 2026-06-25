"""Tests for dream/job.py — DreamJob (78a sleep pass only)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_memory.dream.job import DreamJob


def _make_job(timeout: int = 60):
    dream_store = AsyncMock()
    dream_store.create_run = AsyncMock(return_value=uuid4())
    dream_store.finish_run = AsyncMock()
    dream_store.write_journal_entry = AsyncMock()
    job = DreamJob(
        pool=MagicMock(),
        embedder=MagicMock(),
        consolidator=MagicMock(),
        dream_store=dream_store,
        settings={"dream": {"job_timeout_seconds": timeout}},
    )
    return job, dream_store


async def test_run_completes_and_writes_journal():
    job, dream_store = _make_job()
    with patch.object(
        job._sleep_pass,
        "run",
        new=AsyncMock(return_value={"episodes_scored": 3, "episodes_replayed": 1, "duration_ms": 10}),
    ):
        await job.run()
    dream_store.finish_run.assert_awaited_once()
    dream_store.write_journal_entry.assert_awaited_once()


async def test_run_records_timeout_error():
    job, dream_store = _make_job()
    with patch(
        "ze_memory.dream.job.asyncio.wait_for",
        new=AsyncMock(side_effect=asyncio.TimeoutError()),
    ):
        await job.run()

    finish_kwargs = dream_store.finish_run.call_args.kwargs
    assert finish_kwargs["error"] is not None
    assert "timed out" in finish_kwargs["error"]
    dream_store.write_journal_entry.assert_not_awaited()
