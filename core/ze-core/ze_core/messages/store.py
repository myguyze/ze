from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import asyncpg

from ze_core.messages.types import Message


class MessageStore(Protocol):
    async def save(self, message: Message) -> None: ...
    async def list_since(self, since: datetime, limit: int = 100) -> list[Message]: ...
    async def mark_read(self, ids: list[UUID]) -> None: ...
    async def list_unread(self) -> list[Message]: ...


class PostgresMessageStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def save(self, message: Message) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO messages (id, role, text, components, read, thread_id, created_at)
                VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                ON CONFLICT DO NOTHING
                """,
                message.id,
                message.role,
                message.text,
                json.dumps(message.components),
                message.read,
                message.thread_id,
                message.created_at,
            )

    async def list_since(self, since: datetime, limit: int = 100) -> list[Message]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, text, components, read, thread_id, created_at
                FROM messages
                WHERE created_at > $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                since,
                limit,
            )
        return [_row_to_message(r) for r in rows]

    async def mark_read(self, ids: list[UUID]) -> None:
        if not ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET read = TRUE WHERE id = ANY($1)",
                ids,
            )

    async def list_unread(self) -> list[Message]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, text, components, read, thread_id, created_at
                FROM messages
                WHERE NOT read
                ORDER BY created_at ASC
                """,
            )
        return [_row_to_message(r) for r in rows]


def _row_to_message(row: asyncpg.Record) -> Message:
    components = row["components"]
    if isinstance(components, str):
        components = json.loads(components)
    elif components is None:
        components = []
    return Message(
        id=row["id"],
        role=row["role"],
        text=row["text"],
        components=components,
        read=row["read"],
        thread_id=row["thread_id"],
        created_at=row["created_at"],
    )
