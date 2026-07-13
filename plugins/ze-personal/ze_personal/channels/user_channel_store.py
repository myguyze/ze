import asyncpg

from ze_logging import get_logger
from ze_personal.channels.types import UserChannel


def _channel_from_row(row: asyncpg.Record) -> UserChannel:
    return UserChannel(
        id=row["id"],
        channel_id=row["channel_id"],
        channel_type=row["channel_type"],
        handle=row["handle"],
        display_name=row["display_name"],
        is_default_outbound=row["is_default_outbound"],
        poll_enabled=row["poll_enabled"],
        created_at=row["created_at"],
    )


class UserChannelStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._log = get_logger(__name__)

    async def upsert(self, channel: UserChannel) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_channels
                    (id, channel_id, channel_type, handle, display_name,
                     is_default_outbound, poll_enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (channel_id) DO UPDATE SET
                    handle             = EXCLUDED.handle,
                    poll_enabled       = EXCLUDED.poll_enabled,
                    display_name       = COALESCE(user_channels.display_name, EXCLUDED.display_name)
                """,
                channel.id,
                channel.channel_id,
                channel.channel_type,
                channel.handle,
                channel.display_name,
                channel.is_default_outbound,
                channel.poll_enabled,
            )

    async def list_all(self) -> list[UserChannel]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM user_channels ORDER BY created_at ASC"
            )
        return [_channel_from_row(r) for r in rows]

    async def get_default_outbound(self, channel_type: str) -> UserChannel | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM user_channels
                WHERE channel_type = $1 AND is_default_outbound = TRUE
                LIMIT 1
                """,
                channel_type,
            )
        return _channel_from_row(row) if row else None

    async def set_default_outbound(self, channel_id: str) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT channel_type FROM user_channels WHERE channel_id = $1",
                    channel_id,
                )
                if row is None:
                    return
                channel_type = row["channel_type"]
                await conn.execute(
                    """
                    UPDATE user_channels
                    SET is_default_outbound = FALSE
                    WHERE channel_type = $1
                    """,
                    channel_type,
                )
                await conn.execute(
                    "UPDATE user_channels SET is_default_outbound = TRUE WHERE channel_id = $1",
                    channel_id,
                )

    async def set_poll_enabled(self, channel_id: str, enabled: bool) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_channels SET poll_enabled = $1 WHERE channel_id = $2",
                enabled,
                channel_id,
            )

    async def set_display_name(self, channel_id: str, display_name: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE user_channels SET display_name = $1 WHERE channel_id = $2",
                display_name,
                channel_id,
            )

    async def get(self, channel_id: str) -> UserChannel | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_channels WHERE channel_id = $1", channel_id
            )
        return _channel_from_row(row) if row else None
