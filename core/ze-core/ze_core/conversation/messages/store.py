from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Protocol
from uuid import UUID

import asyncpg

from ze_core.conversation.messages.types import Message, MessageTrace, MemoryChunkTrace, ToolCallTrace


class MessageStore(Protocol):
    async def save(self, message: Message) -> None: ...
    async def list_since(self, since: datetime, limit: int = 100) -> list[Message]: ...
    async def list_by_thread(self, thread_id: str, limit: int = 200) -> list[Message]: ...
    async def mark_read(self, ids: list[UUID]) -> None: ...
    async def list_unread(self, thread_id: str | None = None) -> list[Message]: ...
    async def save_trace(self, message_id: UUID, trace: MessageTrace) -> None: ...
    async def get_trace(self, message_id: UUID) -> MessageTrace | None: ...
    async def list_with_agent(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[UUID, str, datetime]]: ...


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

    async def list_by_thread(self, thread_id: str, limit: int = 200) -> list[Message]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, text, components, read, thread_id, created_at
                FROM messages
                WHERE thread_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                thread_id,
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

    async def list_unread(self, thread_id: str | None = None) -> list[Message]:
        async with self._pool.acquire() as conn:
            if thread_id:
                rows = await conn.fetch(
                    """
                    SELECT id, role, text, components, read, thread_id, created_at
                    FROM messages
                    WHERE NOT read AND thread_id = $1
                    ORDER BY created_at ASC
                    """,
                    thread_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, role, text, components, read, thread_id, created_at
                    FROM messages
                    WHERE NOT read
                    ORDER BY created_at ASC
                    """,
                )
        return [_row_to_message(r) for r in rows]

    async def save_trace(self, message_id: UUID, trace: MessageTrace) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET trace = $1::jsonb WHERE id = $2",
                asdict(trace),
                message_id,
            )

    async def get_trace(self, message_id: UUID) -> MessageTrace | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT trace FROM messages WHERE id = $1", message_id
            )
        if row is None or row["trace"] is None:
            return None
        data = row["trace"]
        if isinstance(data, str):
            data = json.loads(data)
        return _parse_trace(data)

    async def list_with_agent(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[UUID, str, datetime]]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, trace->>'agent' AS agent, created_at
                FROM messages
                WHERE trace IS NOT NULL
                  AND created_at >= $1
                  AND created_at < $2
                ORDER BY created_at ASC
                """,
                start,
                end,
            )
        return [(r["id"], r["agent"], r["created_at"]) for r in rows]


def _parse_trace(data: dict) -> MessageTrace:
    return MessageTrace(
        agent=data["agent"],
        routing_method=data["routing_method"],
        confidence=data["confidence"],
        score_gap=data["score_gap"],
        is_compound=data["is_compound"],
        subtasks=data.get("subtasks", []),
        memory_chunks=[
            MemoryChunkTrace(**c) for c in data.get("memory_chunks", [])
        ],
        tool_calls=[
            ToolCallTrace(**t) for t in data.get("tool_calls", [])
        ],
        total_duration_ms=data.get("total_duration_ms", 0),
    )


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
