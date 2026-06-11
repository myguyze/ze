import asyncpg

from ze_prospecting.store import ProspectCampaignStore


async def recover_stale_campaigns(pool: asyncpg.Pool, timeout_minutes: int = 10) -> None:
    await ProspectCampaignStore(pool).recover_stale(timeout_minutes)
