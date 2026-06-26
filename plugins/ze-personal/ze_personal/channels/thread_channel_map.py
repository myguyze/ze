import asyncpg

from ze_logging import get_logger


class ThreadChannelMap:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._log = get_logger(__name__)

    async def get(self, thread_id: str) -> str | None:
        """Return channel_id that owns this thread, or None if unknown."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT channel_id FROM thread_channel_map WHERE thread_id = $1",
                thread_id,
            )

    async def set(self, thread_id: str, channel_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO thread_channel_map (thread_id, channel_id, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (thread_id) DO UPDATE
                    SET channel_id = EXCLUDED.channel_id,
                        updated_at = NOW()
                """,
                thread_id,
                channel_id,
            )
