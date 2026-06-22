"""Relevance model — projects user memory into a weighted interest fingerprint.

The RelevanceSet is computed on demand (cached, short TTL) from:
  - Profile facets (topics, preferences, news_interests)
  - Explicit preference facts (news_interest_*, topic_interest_*)
  - Active goal titles
  - Entities mentioned in recent episodes
  - Negative preferences / exclusions (zeroed from the set)

The score() method is pure math — no LLM, no DB — so it can run on every
ingested signal cheaply as part of the admission gate (Phase 56).
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ze_logging import get_logger
from ze_memory.types import RelevanceEntry, RelevanceScore, RelevanceSet

log = get_logger(__name__)

_PROFILE_INCLUDE_KEYS = frozenset(
    {"topics", "preferences", "news_preferences", "news_interests"}
)
_PROFILE_EXCLUDE_KEYS = frozenset({"news_exclusions"})
_PROFILE_DEMOTE_KEY = "topic_relevance_demotions"
_DEMOTION_MULTIPLIER = 0.5
_INCLUDE_FACT_PREFIXES = ("news_interest", "interest_news", "topic_interest")
_EXCLUDE_PATTERNS = (
    "don't show",
    "do not show",
    "not interested",
    "avoid",
    "stop showing",
)


def _normalize(key: str) -> str:
    return key.strip().lower()


def _split_topics(value: str) -> list[str]:
    parts = re.split(r"\s*(?:,|;|\||/|\band\b)\s*", value)
    return [p.strip(" :.-") for p in parts if p.strip(" :.-")]


def _merge_entry(
    entries: dict[str, RelevanceEntry],
    key: str,
    new_entry: RelevanceEntry,
) -> None:
    existing = entries.get(key)
    if existing is None:
        entries[key] = new_entry
        return
    merged_weight = min(1.0, max(existing.weight, new_entry.weight))
    merged_sources = list({*existing.sources, *new_entry.sources})
    entries[key] = RelevanceEntry(
        key=existing.key,
        kind=existing.kind,
        weight=merged_weight,
        sources=merged_sources,
    )


class RelevanceModel:
    def __init__(
        self,
        memory_store: Any,
        goal_provider: Any | None = None,
        *,
        episode_lookback_days: int = 30,
        cache_ttl_minutes: int = 30,
    ) -> None:
        self._memory_store = memory_store
        self._goal_provider = goal_provider
        self._episode_lookback_days = episode_lookback_days
        self._cache_ttl_minutes = cache_ttl_minutes
        self._cached: RelevanceSet | None = None
        self._cache_built_at: datetime | None = None

    async def build(self) -> RelevanceSet:
        now = datetime.now(timezone.utc)
        if self._cached is not None and self._cache_built_at is not None:
            age_minutes = (now - self._cache_built_at).total_seconds() / 60
            if age_minutes < self._cache_ttl_minutes:
                return self._cached

        entries: dict[str, RelevanceEntry] = {}
        exclusions: set[str] = set()
        demotions: set[str] = set()

        await self._add_profile_entries(entries, exclusions, demotions)
        await self._add_fact_entries(entries, exclusions)
        await self._add_goal_entries(entries)
        await self._add_episode_entity_entries(entries)

        for key in exclusions:
            entries.pop(key, None)

        for key in demotions:
            if key in entries:
                e = entries[key]
                entries[key] = RelevanceEntry(
                    key=e.key,
                    kind=e.kind,
                    weight=e.weight * _DEMOTION_MULTIPLIER,
                    sources=[*e.sources, "feedback_demoted"],
                )

        rset = RelevanceSet(entries=entries, built_at=now)
        self._cached = rset
        self._cache_built_at = now
        log.debug(
            "relevance_set_built",
            entries=len(entries),
            exclusions=len(exclusions),
        )
        return rset

    def score(
        self,
        rset: RelevanceSet,
        entities: list[str],
        topics: list[str],
    ) -> RelevanceScore:
        keys_to_check = {_normalize(k) for k in entities + topics if k}
        total = 0.0
        contributions: list[str] = []

        for key in keys_to_check:
            entry = rset.entries.get(key)
            if entry is not None:
                total += entry.weight
                sources_str = ", ".join(entry.sources)
                contributions.append(
                    f"{entry.key} (via {sources_str}: {entry.weight:.2f})"
                )

        return RelevanceScore(value=min(1.0, total), contributions=contributions)

    def invalidate_cache(self) -> None:
        self._cached = None
        self._cache_built_at = None

    # ── private builders ──────────────────────────────────────────────────────

    async def _add_profile_entries(
        self,
        entries: dict[str, RelevanceEntry],
        exclusions: set[str],
        demotions: set[str],
    ) -> None:
        try:
            profile = await self._memory_store.get_profile()
        except Exception as exc:
            log.warning("relevance_profile_fetch_failed", error=str(exc))
            return

        for facet in profile:
            key = getattr(facet, "key", "")
            value = getattr(facet, "value", "")
            confidence = getattr(facet, "confidence", 1.0)
            if confidence < 0.5:
                continue

            if key in _PROFILE_EXCLUDE_KEYS:
                for topic in _split_topics(value):
                    exclusions.add(_normalize(topic))
                continue

            if key == _PROFILE_DEMOTE_KEY:
                for topic in _split_topics(value):
                    demotions.add(_normalize(topic))
                continue

            if key not in _PROFILE_INCLUDE_KEYS:
                continue

            for topic in _split_topics(value):
                nk = _normalize(topic)
                if not nk:
                    continue
                _merge_entry(
                    entries,
                    nk,
                    RelevanceEntry(key=topic, kind="topic", weight=0.8, sources=["profile"]),
                )

    async def _add_fact_entries(
        self,
        entries: dict[str, RelevanceEntry],
        exclusions: set[str],
    ) -> None:
        try:
            facts = await self._memory_store.list_recent_facts(days=365, limit=100)
        except Exception as exc:
            log.warning("relevance_fact_fetch_failed", error=str(exc))
            return

        for fact in facts:
            predicate = getattr(fact, "predicate", "")
            value = getattr(fact, "value", "")
            confidence = getattr(fact, "confidence", 1.0)
            if getattr(fact, "contradicted", False) or confidence < 0.5:
                continue

            combined = f"{predicate} {value}".lower()
            if any(pattern in combined for pattern in _EXCLUDE_PATTERNS):
                exclusions.add(_normalize(value))
                continue

            if not predicate.lower().startswith(_INCLUDE_FACT_PREFIXES):
                continue

            for topic in _split_topics(value):
                nk = _normalize(topic)
                if not nk:
                    continue
                _merge_entry(
                    entries,
                    nk,
                    RelevanceEntry(
                        key=topic,
                        kind="topic",
                        weight=0.85,
                        sources=["explicit_preference"],
                    ),
                )

    async def _add_goal_entries(self, entries: dict[str, RelevanceEntry]) -> None:
        if self._goal_provider is None:
            return
        try:
            goal_titles = await self._goal_provider.list_active_goal_titles()
        except Exception as exc:
            log.warning("relevance_goal_fetch_failed", error=str(exc))
            return

        for title in goal_titles:
            nk = _normalize(title)
            if not nk:
                continue
            _merge_entry(
                entries,
                nk,
                RelevanceEntry(key=title, kind="topic", weight=0.6, sources=["active_goal"]),
            )

    async def _add_episode_entity_entries(
        self, entries: dict[str, RelevanceEntry]
    ) -> None:
        try:
            episodes = await self._memory_store.list_recent_episodes(
                days=self._episode_lookback_days,
                limit=100,
            )
        except Exception as exc:
            log.warning("relevance_episode_fetch_failed", error=str(exc))
            return

        entity_ids: set = set()
        for ep in episodes:
            for eid in getattr(ep, "linked_entity_ids", []):
                entity_ids.add(eid)

        if not entity_ids:
            return

        pool = getattr(self._memory_store, "pool", None) or getattr(
            self._memory_store, "_pool", None
        )
        if pool is None:
            return

        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT canonical_name, entity_type FROM memory_entities"
                    " WHERE id = ANY($1::uuid[])",
                    [str(eid) for eid in entity_ids],
                )
            for row in rows:
                nk = _normalize(row["canonical_name"])
                if not nk:
                    continue
                _merge_entry(
                    entries,
                    nk,
                    RelevanceEntry(
                        key=row["canonical_name"],
                        kind="entity",
                        weight=0.5,
                        sources=["recent_episode"],
                    ),
                )
        except Exception as exc:
            log.warning("relevance_episode_entity_lookup_failed", error=str(exc))
