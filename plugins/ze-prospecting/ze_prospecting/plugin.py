from __future__ import annotations

import asyncpg

from ze_core.logging import get_logger
from ze_core.plugin import ZePlugin
from ze_core.proactive.scheduler import ProactiveScheduler
from ze_core.settings import Settings
from ze_prospecting.jobs.campaigns import recover_stale_campaigns
from ze_prospecting.store import ProspectCampaignStore
from ze_prospecting.types import ProspectingSettings

log = get_logger(__name__)


class ProspectingPlugin(ZePlugin):
    """Registers the prospecting agent, campaign store, and recovery job."""

    def __init__(
        self,
        pool: asyncpg.Pool,
        prospecting_settings: ProspectingSettings | None = None,
    ) -> None:
        self._pool = pool
        self._prospecting_settings = prospecting_settings or ProspectingSettings.from_env()
        self.campaign_store = ProspectCampaignStore(pool=pool)

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_prospecting.agents.tools",
            "ze_prospecting.agents.agent",
        ]

    def register_proactive_jobs(
        self,
        scheduler: ProactiveScheduler,
        settings: Settings,
        *,
        consolidation_enabled: bool = True,
    ) -> None:
        if not consolidation_enabled:
            return
        timeout = self._prospecting_settings.stale_timeout_minutes
        scheduler.add_cron_job(
            fn=lambda: recover_stale_campaigns(self._pool, timeout),
            cron="*/15 * * * *",
            job_id="recover_stale_campaigns",
        )
        log.info("stale_campaign_recovery_scheduled")

    async def recover_stale_on_startup(self) -> None:
        await recover_stale_campaigns(
            self._pool,
            self._prospecting_settings.stale_timeout_minutes,
        )
