from datetime import datetime, timedelta, timezone

import asyncpg

from ze_logging import get_logger


class ChannelWatermarkStore:
    DEFAULT_LOOKBACK_HOURS = 24

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._log = get_logger(__name__)

    async def get(self, channel_id: str) -> datetime:
        """Return last polled time, or 24 h ago if never polled."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_polled_at FROM user_channel_watermarks WHERE channel_id = $1",
                channel_id,
            )
        if row is None:
            return datetime.now(timezone.utc) - timedelta(hours=self.DEFAULT_LOOKBACK_HOURS)
        return row["last_polled_at"]

    async def set(self, channel_id: str, polled_at: datetime) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_channel_watermarks (channel_id, last_polled_at)
                VALUES ($1, $2)
                ON CONFLICT (channel_id) DO UPDATE SET last_polled_at = EXCLUDED.last_polled_at
                """,
                channel_id,
                polled_at,
            )
