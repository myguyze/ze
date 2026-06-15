from __future__ import annotations

import json
import math
import re
from datetime import datetime

import asyncpg
import numpy as np
from sentence_transformers import SentenceTransformer

from ze_agents.logging import get_logger
from ze_news.types import (
    Article,
    CredibilityFlag,
    CredibilityReport,
    FLAG_CONFIDENCE,
    NewsPreference,
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
                    ON CONFLICT (url) DO UPDATE SET fetched_at = now()
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

    async def last_fetched_at(self, source_key: str) -> datetime | None:
        """When this source was last synced (max article fetched_at)."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                """
                SELECT MAX(fetched_at)
                FROM news_articles
                WHERE source_key = $1
                """,
                source_key,
            )

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
        include_preferences = [
            p for p in ctx.preferences
            if p.polarity == "include" and p.topic.strip()
        ]
        query_preferences = [p for p in include_preferences if p.source == "query"]
        has_structured_preferences = bool(ctx.preferences)

        if has_structured_preferences:
            has_enough_preferences = (
                len(include_preferences) >= min_facts or bool(query_preferences)
            )
            if not has_enough_preferences:
                articles = await self.get_recent(limit=limit, tags=tags)
                articles = self._apply_exclusions(articles, ctx.exclusions)
                return articles, []

            multiplier = max(ctx.candidate_multiplier, 1)
            candidates = await self.get_recent(limit=limit * multiplier, tags=tags)
            candidates = self._apply_exclusions(candidates, ctx.exclusions)
            scored = self._score_candidates(candidates, ctx)
            scored.sort(key=lambda x: x[1], reverse=True)
            ranked = self._apply_topic_cap([a for a, _ in scored], ctx.max_per_topic)
            return self._split_ranked(ranked, limit, ctx.explore_ratio)

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

    def _score_candidates(
        self,
        articles: list[Article],
        ctx: PersonalizationContext,
    ) -> list[tuple[Article, float]]:
        include_preferences = [
            p for p in ctx.preferences
            if p.polarity == "include" and p.topic.strip()
        ]
        query_preferences = [p for p in include_preferences if p.source == "query"]
        stored_preferences = [p for p in include_preferences if p.source != "query"]

        query_vectors = [
            (p, self._embedder.encode(p.topic))
            for p in query_preferences
        ]
        preference_vectors = [
            (p, self._embedder.encode(p.topic))
            for p in stored_preferences
        ]

        newest = max((a.published_at for a in articles), default=None)
        oldest = min((a.published_at for a in articles), default=None)

        scored: list[tuple[Article, float]] = []
        for article in articles:
            article_vec = self._embedder.encode(f"{article.title}. {article.summary}")
            query_score = _weighted_similarity(article_vec, query_vectors)
            preference_score = _weighted_similarity(article_vec, preference_vectors)
            freshness_score = _freshness_score(article.published_at, oldest, newest)
            scored.append((
                article,
                (1.5 * query_score) + preference_score + (0.1 * freshness_score),
            ))
        return scored

    def _apply_topic_cap(
        self,
        articles: list[Article],
        max_per_topic: int,
    ) -> list[Article]:
        if max_per_topic <= 0:
            return articles

        counts: dict[str, int] = {}
        capped: list[Article] = []
        for article in articles:
            topic = _article_topic(article)
            count = counts.get(topic, 0)
            if count >= max_per_topic:
                continue
            counts[topic] = count + 1
            capped.append(article)
        return capped

    def _split_ranked(
        self,
        ranked: list[Article],
        limit: int,
        explore_ratio: float,
    ) -> tuple[list[Article], list[Article]]:
        n_relevant = math.ceil((1 - explore_ratio) * limit)
        relevant_articles = ranked[:n_relevant]
        n_discovery = limit - len(relevant_articles)
        discovery_articles = sorted(
            ranked[n_relevant:n_relevant + n_discovery],
            key=lambda a: a.published_at,
            reverse=True,
        )
        return relevant_articles, discovery_articles

    def _apply_exclusions(
        self,
        articles: list[Article],
        exclusions: list[str],
    ) -> list[Article]:
        if not exclusions:
            return articles
        patterns: list[re.Pattern[str]] = []
        seen: set[str] = set()
        for term in exclusions:
            for pattern in _exclusion_term_patterns(term):
                key = pattern.pattern
                if key in seen:
                    continue
                seen.add(key)
                patterns.append(pattern)
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


def _weighted_similarity(
    article_vec: object,
    weighted_vectors: list[tuple[NewsPreference, object]],
) -> float:
    if not weighted_vectors:
        return 0.0
    av = np.array(article_vec, dtype=float)
    scores = [
        preference.weight * _cosine(av, np.array(vec, dtype=float))
        for preference, vec in weighted_vectors
    ]
    return max(scores, default=0.0)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = np.linalg.norm(a)
    b_norm = np.linalg.norm(b)
    if a_norm == 0 or b_norm == 0:
        return 0.0
    return float(np.dot(a, b) / (a_norm * b_norm))


def _freshness_score(
    published_at: datetime,
    oldest: datetime | None,
    newest: datetime | None,
) -> float:
    if oldest is None or newest is None or oldest == newest:
        return 0.0
    total = (newest - oldest).total_seconds()
    if total <= 0:
        return 0.0
    return (published_at - oldest).total_seconds() / total


def _article_topic(article: Article) -> str:
    if article.tags:
        return article.tags[0].lower()
    title = article.title.strip().lower()
    return title.split()[0] if title else article.source_key.lower()


def _exclusion_term_patterns(term: str) -> list[re.Pattern[str]]:
    """Word-boundary patterns for an exclusion term and simple singular/plural variants."""
    term = term.strip()
    if not term:
        return []

    variants: list[str] = [term]
    lower = term.lower()
    if lower.endswith("ies") and len(lower) > 4:
        variants.append(lower[:-3] + "y")
    elif lower.endswith("es") and len(lower) > 3 and not lower.endswith("ss"):
        variants.append(lower[:-2])
    elif lower.endswith("s") and len(lower) > 2 and not lower.endswith("ss"):
        variants.append(lower[:-1])
    else:
        variants.append(lower + "s")
        if lower.endswith("y") and len(lower) > 2:
            variants.append(lower[:-1] + "ies")

    return [
        re.compile(r"\b" + re.escape(variant) + r"\b", re.IGNORECASE)
        for variant in variants
        if variant
    ]
