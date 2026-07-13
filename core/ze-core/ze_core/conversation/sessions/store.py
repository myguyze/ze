"""Chat session metadata — one row per conversation thread.

``sessions.id`` is the canonical conversation identifier. It matches
``messages.thread_id``, LangGraph ``configurable.thread_id``, and
``AgentState.session_id`` on the same turn.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

import asyncpg

from ze_core.conversation.sessions.types import (
    Session,
    SessionListPage,
    SessionSearchHit,
)

_FTS_SEARCH_SQL = """
WITH q AS (
    SELECT plainto_tsquery('simple', $1) AS tsq
),
hits AS (
    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'message'::text AS match_source,
        ts_rank(to_tsvector('simple', coalesce(m.text, '')), q.tsq) AS rank,
        ts_headline(
            'simple',
            coalesce(m.text, ''),
            q.tsq,
            'MaxFragments=1, MaxWords=20, MinWords=8'
        ) AS snippet
    FROM messages m
    INNER JOIN sessions s ON s.id = m.thread_id
    CROSS JOIN q
    WHERE m.text IS NOT NULL
      AND q.tsq IS NOT NULL
      AND q.tsq <> ''::tsquery
      AND to_tsvector('simple', m.text) @@ q.tsq

    UNION ALL

    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'metadata'::text AS match_source,
        ts_rank(
            to_tsvector('simple', coalesce(s.title, '') || ' ' || coalesce(s.preview, '')),
            q.tsq
        ) AS rank,
        ts_headline(
            'simple',
            coalesce(s.title, '') || ' ' || coalesce(s.preview, ''),
            q.tsq,
            'MaxFragments=1, MaxWords=20, MinWords=8'
        ) AS snippet
    FROM sessions s
    CROSS JOIN q
    WHERE q.tsq IS NOT NULL
      AND q.tsq <> ''::tsquery
      AND to_tsvector('simple', coalesce(s.title, '') || ' ' || coalesce(s.preview, '')) @@ q.tsq

    UNION ALL

    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'summary'::text AS match_source,
        ts_rank(to_tsvector('simple', mss.summary), q.tsq) AS rank,
        ts_headline(
            'simple',
            mss.summary,
            q.tsq,
            'MaxFragments=1, MaxWords=20, MinWords=8'
        ) AS snippet
    FROM memory_session_summaries mss
    INNER JOIN sessions s ON s.id = mss.session_id
    CROSS JOIN q
    WHERE q.tsq IS NOT NULL
      AND q.tsq <> ''::tsquery
      AND to_tsvector('simple', mss.summary) @@ q.tsq
),
ranked AS (
    SELECT DISTINCT ON (id)
        id,
        title,
        preview,
        title_source,
        created_at,
        last_active_at,
        match_source,
        rank,
        snippet
    FROM hits
    ORDER BY id, rank DESC
)
SELECT
    id,
    title,
    preview,
    title_source,
    created_at,
    last_active_at,
    match_source,
    rank,
    snippet
FROM ranked
ORDER BY rank DESC, last_active_at DESC
LIMIT $2
"""

_ILIKE_SEARCH_SQL = """
WITH hits AS (
    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'message'::text AS match_source,
        1.0::float AS rank,
        substring(m.text FROM 1 FOR 120) AS snippet
    FROM messages m
    INNER JOIN sessions s ON s.id = m.thread_id
    WHERE m.text IS NOT NULL AND m.text ILIKE $1

    UNION ALL

    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'metadata'::text AS match_source,
        0.8::float AS rank,
        coalesce(s.title, s.preview) AS snippet
    FROM sessions s
    WHERE coalesce(s.title, '') ILIKE $1 OR coalesce(s.preview, '') ILIKE $1

    UNION ALL

    SELECT
        s.id,
        s.title,
        s.preview,
        s.title_source,
        s.created_at,
        s.last_active_at,
        'summary'::text AS match_source,
        0.7::float AS rank,
        substring(mss.summary FROM 1 FOR 120) AS snippet
    FROM memory_session_summaries mss
    INNER JOIN sessions s ON s.id = mss.session_id
    WHERE mss.summary ILIKE $1
),
ranked AS (
    SELECT DISTINCT ON (id)
        id,
        title,
        preview,
        title_source,
        created_at,
        last_active_at,
        match_source,
        rank,
        snippet
    FROM hits
    ORDER BY id, rank DESC
)
SELECT
    id,
    title,
    preview,
    title_source,
    created_at,
    last_active_at,
    match_source,
    rank,
    snippet
FROM ranked
ORDER BY rank DESC, last_active_at DESC
LIMIT $2
"""


class SessionStore(Protocol):
    async def upsert(
        self,
        session_id: str,
        *,
        title: str | None = None,
        preview: str | None = None,
        title_source: str | None = None,
        update_title: bool = False,
    ) -> None: ...

    async def create(self, session_id: str, *, title: str | None = None) -> Session: ...

    async def list_page(
        self,
        *,
        limit: int = 30,
        before: datetime | None = None,
    ) -> SessionListPage: ...

    async def search(
        self, query: str, *, limit: int = 20
    ) -> list[SessionSearchHit]: ...

    async def get(self, session_id: str) -> Session | None: ...


class PostgresSessionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert(
        self,
        session_id: str,
        *,
        title: str | None = None,
        preview: str | None = None,
        title_source: str | None = None,
        update_title: bool = False,
    ) -> None:
        now = datetime.now(timezone.utc)
        title_expr = (
            "EXCLUDED.title"
            if update_title
            else "COALESCE(sessions.title, EXCLUDED.title)"
        )
        title_source_expr = (
            "EXCLUDED.title_source"
            if update_title
            else "COALESCE(sessions.title_source, EXCLUDED.title_source)"
        )
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"""
                INSERT INTO sessions (id, title, preview, title_source, created_at, last_active_at)
                VALUES ($1, $2, $3, $4, $5, $5)
                ON CONFLICT (id) DO UPDATE SET
                    title = {title_expr},
                    preview = COALESCE(EXCLUDED.preview, sessions.preview),
                    title_source = {title_source_expr},
                    last_active_at = EXCLUDED.last_active_at
                """,
                session_id,
                title,
                preview,
                title_source,
                now,
            )

    async def create(self, session_id: str, *, title: str | None = None) -> Session:
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sessions (id, title, preview, title_source, created_at, last_active_at)
                VALUES ($1, $2, NULL, NULL, $3, $3)
                ON CONFLICT (id) DO NOTHING
                """,
                session_id,
                title,
                now,
            )
        return Session(
            id=session_id,
            title=title,
            preview=None,
            title_source=None,
            created_at=now,
            last_active_at=now,
        )

    async def list_page(
        self,
        *,
        limit: int = 30,
        before: datetime | None = None,
    ) -> SessionListPage:
        if before is None:
            before = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, preview, title_source, created_at, last_active_at
                FROM sessions
                WHERE last_active_at < $1
                ORDER BY last_active_at DESC, id DESC
                LIMIT $2
                """,
                before,
                limit,
            )
        items = [_row_to_session(r) for r in rows]
        next_before = items[-1].last_active_at if len(items) >= limit else None
        return SessionListPage(items=items, next_before=next_before)

    async def search(self, query: str, *, limit: int = 20) -> list[SessionSearchHit]:
        trimmed = query.strip()
        if len(trimmed) < 2:
            return []

        async with self._pool.acquire() as conn:
            tsq_row = await conn.fetchrow(
                "SELECT plainto_tsquery('simple', $1) AS tsq",
                trimmed,
            )
            tsq = tsq_row["tsq"] if tsq_row else None
            if tsq:
                rows = await conn.fetch(_FTS_SEARCH_SQL, trimmed, limit)
            else:
                pattern = f"%{_escape_ilike(trimmed)}%"
                rows = await conn.fetch(_ILIKE_SEARCH_SQL, pattern, limit)

        return [_row_to_search_hit(r) for r in rows]

    async def get(self, session_id: str) -> Session | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, title, preview, title_source, created_at, last_active_at
                FROM sessions
                WHERE id = $1
                """,
                session_id,
            )
        return _row_to_session(row) if row else None


def _escape_ilike(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _row_to_session(row: asyncpg.Record) -> Session:
    return Session(
        id=row["id"],
        title=row["title"],
        preview=row["preview"],
        title_source=row["title_source"],
        created_at=row["created_at"],
        last_active_at=row["last_active_at"],
    )


def _row_to_search_hit(row: asyncpg.Record) -> SessionSearchHit:
    session = _row_to_session(row)
    return SessionSearchHit(
        session=session,
        match_source=row["match_source"],
        snippet=row["snippet"],
        rank=float(row["rank"]),
    )
