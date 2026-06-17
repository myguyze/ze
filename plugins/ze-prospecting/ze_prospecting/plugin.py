from __future__ import annotations

from typing import Any

import asyncpg

from ze_agents.logging import get_logger
from ze_agents.plugin import ZePlugin
from ze_agents.settings import Settings as CoreSettings
from ze_sdk.proactive import ProactiveScheduler
from ze_prospecting.jobs.campaigns import recover_stale_campaigns
from ze_prospecting.store import ProspectCampaignStore
from ze_prospecting.types import ProspectingSettings

log = get_logger(__name__)


class ProspectingPlugin(ZePlugin):
    """Registers the prospecting agent, campaign store, and recovery job."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        settings: CoreSettings,
    ) -> None:
        self._pool = pool
        prospecting_cfg = settings.config.get("prospecting", {})
        if prospecting_cfg:
            self._prospecting_settings = ProspectingSettings(
                max_iterations=int(prospecting_cfg.get("max_iterations", 15)),
                max_loop_tokens=int(prospecting_cfg.get("max_loop_tokens", 24_000)),
                stale_timeout_minutes=int(
                    prospecting_cfg.get("stale_timeout_minutes", 10)
                ),
                browser_delay_ms=int(prospecting_cfg.get("browser_delay_ms", 2000)),
                browser_max_text_chars=int(
                    prospecting_cfg.get("browser_max_text_chars", 8000)
                ),
            )
        else:
            self._prospecting_settings = ProspectingSettings.from_env()
        self.campaign_store = ProspectCampaignStore(pool=pool)

    def data_domains(self):
        from ze_agents.plugin import DataDomain

        async def _export(tbl: str, pool) -> list[dict]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT * FROM {tbl}")
                return [dict(r) for r in rows]

        async def _delete(tbl: str, pool) -> None:
            async with pool.acquire() as conn:
                await conn.execute(f"DELETE FROM {tbl}")

        return [
            DataDomain(
                "prospecting.outreach",
                lambda p: _export("prospect_outreach", p),
                lambda p: _delete("prospect_outreach", p),
                delete_order=10,
            ),
            DataDomain(
                "prospecting.campaigns",
                lambda p: _export("prospect_campaigns", p),
                lambda p: _delete("prospect_campaigns", p),
                delete_order=20,
            ),
        ]

    def agent_deps(self, accumulated: dict) -> dict:
        return {
            ProspectCampaignStore: self.campaign_store,
            ProspectingSettings: self._prospecting_settings,
        }

    def memory_policies(self) -> dict:
        from ze_memory.policies import ProspectingPolicy

        return {"prospecting": ProspectingPolicy()}

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_browser.tool",
            "ze_prospecting.agents.tools",
            "ze_prospecting.agents.agent",
        ]

    def register_proactive_jobs(
        self,
        scheduler: ProactiveScheduler,
        settings: CoreSettings,
        *,
        consolidation_enabled: bool = True,
    ) -> None:
        if not consolidation_enabled:
            return
        timeout = self._prospecting_settings.stale_timeout_minutes
        pool = self._pool

        async def _recover() -> None:
            await recover_stale_campaigns(pool, timeout)

        scheduler.add_cron_job(
            fn=_recover,
            cron="*/15 * * * *",
            job_id="recover_stale_campaigns",
        )
        log.info("stale_campaign_recovery_scheduled")

    async def startup(self, container: Any) -> None:
        await recover_stale_campaigns(
            self._pool,
            self._prospecting_settings.stale_timeout_minutes,
        )
        log.info("stale_campaigns_checked")

    async def shutdown(self) -> None:
        await self.campaign_store.fail_all_running()
