from __future__ import annotations

import base64
from datetime import datetime
from uuid import UUID

import asyncpg

from ze_logging import get_logger
from ze_proactive.types import Notification, NotificationRow

log = get_logger(__name__)


class InvalidCursorError(ValueError):
    """Raised when a pagination cursor cannot be decoded."""


def _encode_cursor(created_at: datetime, id_: str) -> str:
    raw = f"{created_at.isoformat()}|{id_}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, id_ = raw.split("|", 1)
        return datetime.fromisoformat(created_at_str), id_
    except Exception as exc:
        raise InvalidCursorError(f"invalid cursor: {cursor}") from exc


def _row_to_dataclass(row: asyncpg.Record) -> NotificationRow:
    return NotificationRow(
        id=str(row["id"]),
        event_type=row["event_type"],
        source=row["source"],
        title=row["title"],
        body=row["body"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        created_at=row["created_at"],
        read_at=row["read_at"],
    )


def _row_to_notification(
    row: NotificationRow, *, read_override: bool = False
) -> Notification:
    return Notification(
        id=row.id,
        event_type=row.event_type,
        source=row.source,
        title=row.title,
        body=row.body,
        target_type=row.target_type,
        target_id=row.target_id,
        created_at=row.created_at,
        read=read_override or row.read_at is not None,
    )


class NotificationStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        event_type: str,
        source: str,
        title: str,
        body: str,
        target_type: str | None = None,
        target_id: str | None = None,
    ) -> NotificationRow:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO notifications (event_type, source, title, body, target_type, target_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id, event_type, source, title, body, target_type, target_id, created_at, read_at
                """,
                event_type,
                source,
                title,
                body,
                target_type,
                target_id,
            )
        log.debug("notification_created", event_type=event_type, source=source)
        return _row_to_dataclass(row)

    async def list_page(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        unread_only: bool = False,
        mark_read: bool = False,
    ) -> tuple[list[Notification], str | None]:
        limit = max(1, min(limit, 100))
        conditions = []
        params: list[object] = []

        if unread_only:
            conditions.append("read_at IS NULL")

        if cursor is not None:
            created_at, id_ = _decode_cursor(cursor)
            params.extend([created_at, UUID(id_)])
            conditions.append(
                f"(created_at, id) < (${len(params) - 1}, ${len(params)})"
            )

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit + 1)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                rows = await conn.fetch(
                    f"""
                    SELECT id, event_type, source, title, body, target_type, target_id, created_at, read_at
                    FROM notifications
                    {where_clause}
                    ORDER BY created_at DESC, id DESC
                    LIMIT ${len(params)}
                    """,
                    *params,
                )

                page_rows = rows[:limit]
                has_more = len(rows) > limit

                if mark_read and page_rows:
                    ids = [row["id"] for row in page_rows]
                    await conn.execute(
                        "UPDATE notifications SET read_at = NOW() "
                        "WHERE id = ANY($1::uuid[]) AND read_at IS NULL",
                        ids,
                    )

        items = [
            _row_to_notification(_row_to_dataclass(row), read_override=mark_read)
            for row in page_rows
        ]

        next_cursor = None
        if has_more and page_rows:
            last = page_rows[-1]
            next_cursor = _encode_cursor(last["created_at"], str(last["id"]))

        return items, next_cursor

    async def unread_count(self) -> int:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
            )
        return int(row[0]) if row else 0

    async def mark_read(self, id_: str) -> bool:
        """Marks a notification read. Returns False if `id_` does not exist."""
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE notifications SET read_at = NOW() "
                "WHERE id = $1 AND read_at IS NULL",
                UUID(id_),
            )
            if _rowcount(result) > 0:
                return True
            row = await conn.fetchrow(
                "SELECT 1 FROM notifications WHERE id = $1", UUID(id_)
            )
            return row is not None

    async def mark_all_read(self) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE notifications SET read_at = NOW() WHERE read_at IS NULL"
            )
        return _rowcount(result)

    async def exists_recent(
        self,
        *,
        event_type: str,
        target_type: str | None,
        target_id: str | None,
        hours: float,
    ) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM notifications
                WHERE event_type = $1
                AND target_type IS NOT DISTINCT FROM $2
                AND target_id IS NOT DISTINCT FROM $3
                AND created_at > NOW() - ($4 * INTERVAL '1 hour')
                """,
                event_type,
                target_type,
                target_id,
                hours,
            )
        return row is not None

    async def prune_read_older_than(self, days: int = 90) -> int:
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM notifications "
                "WHERE read_at IS NOT NULL AND read_at < NOW() - ($1 * INTERVAL '1 day')",
                days,
            )
        pruned = _rowcount(result)
        log.info("notifications_pruned", pruned=pruned, days=days)
        return pruned


def _rowcount(result: str) -> int:
    # asyncpg command tags look like "UPDATE 3" / "DELETE 3".
    return int(result.split()[-1])
