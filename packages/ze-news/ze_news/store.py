from __future__ import annotations

from datetime import datetime, timezone

import asyncpg
from sentence_transformers import SentenceTransformer

from ze_core.logging import get_logger
from ze_news.types import Article

log = get_logger(__name__)


def _to_pgvector(embedding: object) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _row_to_article(row: asyncpg.Record) -> Article:
    return Article(
        url=row["url"],
        source_key=row["source_key"],
        title=row["title"],
        summary=row["summary"],
        published_at=row["published_at"],
        tags=list(row["tags"] or []),
    )


class NewsStore:
    def __init__(self, pool: asyncpg.Pool, embedder: SentenceTransformer) -> None:
        self._pool = pool
        self._embedder = embedder

    async def upsert(self, articles: list[Article]) -> int:
        if not articles:
            return 0

        new_count = 0
        async with self._pool.acquire() as conn:
            for article in articles:
                text = f"{article.title}. {article.summary}"
                embedding = self._embedder.encode(text)
                vec = _to_pgvector(embedding)

                status = await conn.execute(
                    """
                    INSERT INTO news_articles
                        (url, source_key, title, summary, published_at, tags, embedding)
                    VALUES ($1, $2, $3, $4, $5, $6, $7::vector)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    article.url,
                    article.source_key,
                    article.title,
                    article.summary,
                    article.published_at,
                    article.tags,
                    vec,
                )
                if status == "INSERT 0 1":
                    new_count += 1

        return new_count

    async def search(
        self,
        query: str,
        limit: int = 10,
        tags: list[str] | None = None,
    ) -> list[Article]:
        embedding = self._embedder.encode(query)
        vec = _to_pgvector(embedding)

        tag_filter = "AND tags && $4::text[]" if tags else ""
        params: list = [vec, limit]
        if tags:
            params.append(tags)

        sql = f"""
            SELECT url, source_key, title, summary, published_at, tags
            FROM news_articles
            WHERE TRUE {tag_filter}
            ORDER BY embedding <=> $1::vector, published_at DESC
            LIMIT $2
        """
        if tags:
            sql = f"""
                SELECT url, source_key, title, summary, published_at, tags
                FROM news_articles
                WHERE tags && $3::text[]
                ORDER BY embedding <=> $1::vector, published_at DESC
                LIMIT $2
            """

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, vec, limit, *(params[2:]))
        return [_row_to_article(r) for r in rows]

    async def get_recent(
        self,
        limit: int = 20,
        tags: list[str] | None = None,
    ) -> list[Article]:
        if tags:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags
                FROM news_articles
                WHERE tags && $2::text[]
                ORDER BY published_at DESC
                LIMIT $1
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit, tags)
        else:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags
                FROM news_articles
                ORDER BY published_at DESC
                LIMIT $1
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit)
        return [_row_to_article(r) for r in rows]

    async def prune(self, older_than_days: int) -> int:
        async with self._pool.acquire() as conn:
            status = await conn.execute(
                """
                DELETE FROM news_articles
                WHERE fetched_at < now() - ($1 || ' days')::interval
                """,
                str(older_than_days),
            )
        try:
            return int(status.split()[-1])
        except (ValueError, IndexError):
            return 0
