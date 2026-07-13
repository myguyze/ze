from __future__ import annotations

from ze_logging import get_logger
from ze_proactive.job import proactive_job
from ze_proactive.notification_store import NotificationStore

log = get_logger(__name__)

_DEFAULT_RETENTION_DAYS = 90


@proactive_job
class PruneNotificationsJob:
    """Daily sweep: delete read notifications older than the retention window (FR-015)."""

    job_id = "prune_notifications"

    def __init__(
        self,
        notification_store: NotificationStore,
        *,
        retention_days: int = _DEFAULT_RETENTION_DAYS,
    ) -> None:
        self._store = notification_store
        self._retention_days = retention_days

    async def run(self) -> None:
        pruned = await self._store.prune_read_older_than(self._retention_days)
        log.info("notifications_prune_job_ran", pruned=pruned)
