import asyncpg

from ze.logging import get_logger

log = get_logger(__name__)


async def recover_stale_campaigns(pool: asyncpg.Pool, timeout_minutes: int = 60) -> None:
    await pool.execute(
        """
        UPDATE prospect_campaigns
        SET status = 'failed', completed_at = NOW()
        WHERE status = 'running'
          AND created_at < NOW() - ($1 * INTERVAL '1 minute')
        """,
        timeout_minutes,
    )
    log.info("stale_campaigns_recovered", timeout_minutes=timeout_minutes)
