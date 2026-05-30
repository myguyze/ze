import asyncpg

from ze.logging import get_logger

log = get_logger(__name__)


async def recover_stale_campaigns(pool: asyncpg.Pool, timeout_minutes: int = 60) -> None:
    tag = await pool.execute(
        """
        UPDATE prospect_campaigns
        SET status = 'failed', completed_at = NOW()
        WHERE status = 'running'
          AND created_at < NOW() - ($1 * INTERVAL '1 minute')
        """,
        timeout_minutes,
    )
    parts = tag.split() if isinstance(tag, str) else []
    count = int(parts[-1]) if parts else 0
    if count:
        log.info("stale_campaigns_recovered", count=count, timeout_minutes=timeout_minutes)
