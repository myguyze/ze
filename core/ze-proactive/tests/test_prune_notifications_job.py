from __future__ import annotations

from unittest.mock import AsyncMock

from ze_proactive.jobs.prune_notifications import PruneNotificationsJob


async def test_prune_job_calls_store_with_retention_days():
    store = AsyncMock()
    store.prune_read_older_than = AsyncMock(return_value=5)
    job = PruneNotificationsJob(notification_store=store, retention_days=90)

    await job.run()

    store.prune_read_older_than.assert_awaited_once_with(90)


async def test_prune_job_defaults_to_90_days():
    store = AsyncMock()
    store.prune_read_older_than = AsyncMock(return_value=0)
    job = PruneNotificationsJob(notification_store=store)

    await job.run()

    store.prune_read_older_than.assert_awaited_once_with(90)
