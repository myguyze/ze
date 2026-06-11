from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone

import asyncpg
from sentence_transformers import SentenceTransformer

from ze_core.logging import get_logger
from ze_news.types import (
    Article,
    CredibilityFlag,
    CredibilityReport,
    FLAG_CONFIDENCE,
    PersonalizationContext,
)

log = get_logger(__name__)

_MIN_FACTS_DEFAULT = 5


def _to_pgvector(embedding: object) -> str:
    vals = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
    return "[" + ",".join(str(v) for v in vals) + "]"


def _deserialize_credibility(raw: str | None) -> CredibilityReport | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        flags = [
            CredibilityFlag(
                type=f["type"],
                label=f.get("label", f["type"]),
                detail=f.get("detail", ""),
                source=f.get("source", "llm"),
                confidence=f.get("confidence", FLAG_CONFIDENCE.get(f["type"], "low")),
                lang=f.get("lang", "any"),
            )
            for f in data.get("flags", [])
        ]
        analyzed_at = None
        if data.get("analyzed_at"):
            try:
                analyzed_at = datetime.fromisoformat(data["analyzed_at"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass
        return CredibilityReport(
            flags=flags,
            status=data.get("status", "complete"),
            analyzed_at=analyzed_at,
            model=data.get("model"),
            prompt_version=data.get("prompt_version"),
        )
    except Exception:
        return None


def _serialize_credibility(report: CredibilityReport) -> str:
    return json.dumps({
        "flags": [
            {
                "type": f.type,
                "label": f.label,
                "detail": f.detail,
                "source": f.source,
                "confidence": f.confidence,
                "lang": f.lang,
            }
            for f in report.flags
        ],
        "status": report.status,
        "analyzed_at": report.analyzed_at.isoformat() if report.analyzed_at else None,
        "model": report.model,
        "prompt_version": report.prompt_version,
    })


def _row_to_article(row: asyncpg.Record) -> Article:
    credibility_raw = row["credibility_analysis"] if "credibility_analysis" in row.keys() else None
    return Article(
        url=row["url"],
        source_key=row["source_key"],
        title=row["title"],
        summary=row["summary"],
        published_at=row["published_at"],
        tags=list(row["tags"] or []),
        credibility=_deserialize_credibility(credibility_raw),
    )


class NewsStore:
    def __init__(self, pool: asyncpg.Pool, embedder: SentenceTransformer) -> None:
        self._pool = pool
        self._embedder = embedder

    async def upsert(self, articles: list[Article]) -> list[Article]:
        """Upsert articles. Returns the list of newly inserted articles."""
        if not articles:
            return []

        new_articles: list[Article] = []
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
                    new_articles.append(article)

        return new_articles

    async def update_credibility(self, url: str, report: CredibilityReport) -> None:
        """Write a CredibilityReport to news_articles.credibility_analysis."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE news_articles
                   SET credibility_analysis = $2::jsonb
                 WHERE url = $1
                """,
                url,
                _serialize_credibility(report),
            )

    async def search(
        self,
        query: str,
        limit: int = 10,
        tags: list[str] | None = None,
    ) -> list[Article]:
        embedding = self._embedder.encode(query)
        vec = _to_pgvector(embedding)

        if tags:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags, credibility_analysis
                FROM news_articles
                WHERE tags && $3::text[]
                ORDER BY embedding <=> $1::vector, published_at DESC
                LIMIT $2
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, vec, limit, tags)
        else:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags, credibility_analysis
                FROM news_articles
                ORDER BY embedding <=> $1::vector, published_at DESC
                LIMIT $2
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, vec, limit)
        return [_row_to_article(r) for r in rows]

    async def get_recent(
        self,
        limit: int = 20,
        tags: list[str] | None = None,
    ) -> list[Article]:
        if tags:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags, credibility_analysis
                FROM news_articles
                WHERE tags && $2::text[]
                ORDER BY published_at DESC
                LIMIT $1
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit, tags)
        else:
            sql = """
                SELECT url, source_key, title, summary, published_at, tags, credibility_analysis
                FROM news_articles
                ORDER BY published_at DESC
                LIMIT $1
            """
            async with self._pool.acquire() as conn:
                rows = await conn.fetch(sql, limit)
        return [_row_to_article(r) for r in rows]

    async def get_personalized(
        self,
        ctx: PersonalizationContext,
        limit: int = 20,
        tags: list[str] | None = None,
        min_facts: int = _MIN_FACTS_DEFAULT,
    ) -> tuple[list[Article], list[Article]]:
        if not ctx.interest_text.strip() or ctx.fact_count < min_facts:
            articles = await self.get_recent(limit=limit, tags=tags)
            return articles, []

        candidates = await self.get_recent(limit=limit * 3, tags=tags)
        candidates = self._apply_exclusions(candidates, ctx.exclusions)

        interest_vec = self._embedder.encode(ctx.interest_text)
        scored = self._score_articles(candidates, interest_vec)
        scored.sort(key=lambda x: x[1], reverse=True)

        n_relevant = math.ceil((1 - ctx.explore_ratio) * limit)
        relevant_articles = [a for a, _ in scored[:n_relevant]]

        remaining = [a for a, _ in scored[n_relevant:]]
        n_discovery = limit - len(relevant_articles)
        discovery_articles = sorted(
            remaining[:n_discovery],
            key=lambda a: a.published_at,
            reverse=True,
        )

        return relevant_articles, discovery_articles

    def _score_articles(
        self,
        articles: list[Article],
        interest_vec: object,
    ) -> list[tuple[Article, float]]:
        import numpy as np

        iv = np.array(interest_vec, dtype=float)
        iv_norm = np.linalg.norm(iv)

        results = []
        for article in articles:
            text = f"{article.title}. {article.summary}"
            emb = self._embedder.encode(text)
            av = np.array(emb, dtype=float)
            av_norm = np.linalg.norm(av)
            if iv_norm == 0 or av_norm == 0:
                score = 0.0
            else:
                score = float(np.dot(iv, av) / (iv_norm * av_norm))
            results.append((article, score))
        return results

    def _apply_exclusions(
        self,
        articles: list[Article],
        exclusions: list[str],
    ) -> list[Article]:
        if not exclusions:
            return articles
        patterns = [
            re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
            for term in exclusions
        ]
        return [
            a for a in articles
            if not any(
                p.search(a.title) or p.search(a.summary)
                for p in patterns
            )
        ]

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
