from uuid import UUID

import asyncpg

from ze.channels.types import ChannelHandle, ChannelType
from ze.logging import get_logger


def _handle_from_row(row: asyncpg.Record) -> ChannelHandle:
    return ChannelHandle(
        channel_type=ChannelType(row["channel_type"]),
        handle=row["handle"],
        preferred=row["preferred"],
        verified=row["verified"],
    )


class ContactChannelStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool
        self._log = get_logger(__name__)

    async def get_handles(self, contact_id: UUID) -> list[ChannelHandle]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM contact_channels
                WHERE contact_id = $1
                ORDER BY preferred DESC, created_at ASC
                """,
                contact_id,
            )
        return [_handle_from_row(r) for r in rows]

    async def get_preferred(self, contact_id: UUID) -> ChannelHandle | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM contact_channels
                WHERE contact_id = $1 AND preferred = true
                ORDER BY created_at ASC
                LIMIT 1
                """,
                contact_id,
            )
        return _handle_from_row(row) if row else None

    async def upsert(self, contact_id: UUID, handle: ChannelHandle) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO contact_channels (contact_id, channel_type, handle, preferred, verified)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (contact_id, channel_type, handle) DO UPDATE SET
                    preferred  = EXCLUDED.preferred,
                    verified   = EXCLUDED.verified,
                    updated_at = NOW()
                """,
                contact_id,
                handle.channel_type.value,
                handle.handle,
                handle.preferred,
                handle.verified,
            )
        self._log.debug(
            "contact_channel_upserted",
            contact_id=str(contact_id),
            channel_type=handle.channel_type,
            handle=handle.handle,
        )

    async def set_preferred(self, contact_id: UUID, channel_type: ChannelType) -> None:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE contact_channels
                    SET preferred = false, updated_at = NOW()
                    WHERE contact_id = $1 AND channel_type != $2
                    """,
                    contact_id,
                    channel_type.value,
                )
                await conn.execute(
                    """
                    UPDATE contact_channels
                    SET preferred = true, updated_at = NOW()
                    WHERE contact_id = $1 AND channel_type = $2
                    """,
                    contact_id,
                    channel_type.value,
                )
        self._log.debug(
            "contact_channel_preferred_set",
            contact_id=str(contact_id),
            channel_type=channel_type,
        )

    async def delete(
        self, contact_id: UUID, channel_type: ChannelType, handle: str
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM contact_channels
                WHERE contact_id = $1 AND channel_type = $2 AND handle = $3
                """,
                contact_id,
                channel_type.value,
                handle,
            )
        self._log.debug(
            "contact_channel_deleted",
            contact_id=str(contact_id),
            channel_type=channel_type,
            handle=handle,
        )
