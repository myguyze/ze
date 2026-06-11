from __future__ import annotations

from uuid import UUID

import asyncpg

from ze_core.logging import get_logger

log = get_logger(__name__)


class ProspectCampaignStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, brief: str) -> UUID:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO prospect_campaigns (brief, status) VALUES ($1, 'running') RETURNING id",
                brief,
            )
        return row["id"]

    async def complete(self, campaign_id: UUID, output: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE prospect_campaigns SET status = 'complete', output = $2, completed_at = NOW() WHERE id = $1",
                campaign_id,
                output,
            )

    async def fail(self, campaign_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE prospect_campaigns SET status = 'failed', completed_at = NOW() WHERE id = $1",
                campaign_id,
            )

    async def fail_all_running(self) -> None:
        """Mark every running campaign as failed — called on graceful shutdown."""
        await self._pool.execute(
            "UPDATE prospect_campaigns SET status = 'failed', completed_at = NOW() WHERE status = 'running'"
        )

    async def recover_stale(self, timeout_minutes: int) -> int:
        """Mark running campaigns older than timeout_minutes as failed. Returns count recovered."""
        tag = await self._pool.execute(
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
        return count

    async def increment_found(self, campaign_id: UUID) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE prospect_campaigns SET found_count = found_count + 1 WHERE id = $1",
                campaign_id,
            )

    async def add_outreach(self, campaign_id: UUID, contact_id: UUID, channel: str) -> UUID | None:
        """Insert an outreach record; returns the new row id, or None on conflict."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO prospect_outreach (campaign_id, contact_id, channel, status)
                VALUES ($1, $2, $3, 'pending')
                ON CONFLICT (campaign_id, contact_id) DO NOTHING
                RETURNING id
                """,
                campaign_id,
                contact_id,
                channel,
            )
        return row["id"] if row else None

    async def save_draft(self, campaign_id: UUID, contact_id: UUID, draft: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE prospect_outreach SET draft = $3 WHERE campaign_id = $1 AND contact_id = $2",
                campaign_id,
                contact_id,
                draft,
            )

    async def get_latest_outreach_id(self, contact_id: UUID) -> UUID | None:
        """Return the id of the most recent outreach record for a contact."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM prospect_outreach WHERE contact_id = $1 ORDER BY created_at DESC LIMIT 1",
                contact_id,
            )
        return row["id"] if row else None

    async def log_outreach_event(
        self,
        outreach_id: UUID,
        status: str,
        notes: str,
        ts_column: str | None,
    ) -> None:
        ts_clause = f", {ts_column} = NOW()" if ts_column else ""
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE prospect_outreach SET status = $2, notes = $3{ts_clause} WHERE id = $1",
                outreach_id,
                status,
                notes,
            )
