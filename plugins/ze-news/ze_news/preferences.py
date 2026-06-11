from __future__ import annotations

import re
from typing import Any

from ze_news.types import GoalTitleProvider, NewsPreference, PersonalizationContext

_INCLUDE_PREFIXES = ("news_interest", "interest_news", "topic_interest")
_PROFILE_KEYS = {"topics", "preferences", "news_preferences"}
_NEGATIVE_PATTERNS = (
    "don't show",
    "do not show",
    "not interested",
    "don't care about",
    "avoid",
    "stop showing",
)
_DIAGNOSTIC_PATTERNS = (
    "why do you keep",
    "why are you",
    "why did you",
    "show me the fact",
    "fact that says",
    "stop suggesting",
    "stop showing",
    "do you think i care",
)


class NewsPreferenceBuilder:
    def __init__(
        self,
        memory_store: Any,
        goal_provider: GoalTitleProvider,
        *,
        fact_days: int = 365,
        fact_limit: int = 100,
        min_confidence: float = 0.65,
    ) -> None:
        self._memory_store = memory_store
        self._goal_provider = goal_provider
        self._fact_days = fact_days
        self._fact_limit = fact_limit
        self._min_confidence = min_confidence

    async def build(self, query_text: str) -> PersonalizationContext:
        facts = await self._list_facts()
        profile = await self._get_profile()
        goals = await self._list_goals()

        preferences: list[NewsPreference] = []
        exclusions: list[str] = []

        for fact in facts:
            if not self._fact_is_eligible(fact):
                continue
            preferences.extend(self._preferences_from_fact(fact, exclusions))

        for facet in profile:
            if getattr(facet, "confidence", 1.0) < self._min_confidence:
                continue
            key = getattr(facet, "key", "")
            if key not in _PROFILE_KEYS:
                continue
            for topic in _split_topics(getattr(facet, "value", "")):
                preferences.append(
                    NewsPreference(
                        topic=topic,
                        polarity="include",
                        source="profile",
                        weight=0.6,
                        reason=f"profile topic: {topic}",
                        confidence=getattr(facet, "confidence", 1.0),
                    )
                )

        for goal in goals:
            goal = goal.strip()
            if goal:
                preferences.append(
                    NewsPreference(
                        topic=goal,
                        polarity="include",
                        source="goal",
                        weight=0.5,
                        reason=f"active goal: {goal}",
                    )
                )

        if query_text.strip() and not _is_diagnostic_query(query_text):
            preferences.append(
                NewsPreference(
                    topic=query_text.strip(),
                    polarity="include",
                    source="query",
                    weight=1.0,
                    reason=f"matches current request: {query_text.strip()}",
                )
            )

        for preference in preferences:
            if preference.polarity == "exclude":
                exclusions.append(preference.topic)

        exclusions = _dedupe_terms(exclusions)
        include_preferences = [p for p in preferences if p.polarity == "include"]
        interest_text = " | ".join(
            f"{p.source}:{p.topic}" for p in include_preferences
        )

        return PersonalizationContext(
            interest_text=interest_text,
            exclusions=exclusions,
            fact_count=len(include_preferences),
            query_text=query_text,
            preferences=preferences,
        )

    async def _list_facts(self) -> list[Any]:
        try:
            return await self._memory_store.list_recent_facts(
                days=self._fact_days,
                limit=self._fact_limit,
            )
        except Exception:
            return []

    async def _get_profile(self) -> list[Any]:
        try:
            return await self._memory_store.get_profile()
        except Exception:
            return []

    async def _list_goals(self) -> list[str]:
        try:
            return await self._goal_provider.list_active_goal_titles()
        except Exception:
            return []

    def _fact_is_eligible(self, fact: Any) -> bool:
        if getattr(fact, "contradicted", False):
            return False
        if getattr(fact, "confidence", 1.0) < self._min_confidence:
            return False
        return True

    def _preferences_from_fact(
        self,
        fact: Any,
        exclusions: list[str],
    ) -> list[NewsPreference]:
        predicate = getattr(fact, "predicate", "")
        value = getattr(fact, "value", "")
        predicate_l = predicate.lower()
        combined = f"{predicate} {value}"

        exclusion = _extract_exclusion(combined)
        if exclusion:
            exclusions.append(exclusion)
            return [
                NewsPreference(
                    topic=exclusion,
                    polarity="exclude",
                    source="fact",
                    weight=1.0,
                    reason=f"stored news exclusion: {exclusion}",
                    confidence=getattr(fact, "confidence", 1.0),
                )
            ]

        if not predicate_l.startswith(_INCLUDE_PREFIXES):
            return []

        topics = _split_topics(value)
        return [
            NewsPreference(
                topic=topic,
                polarity="include",
                source="fact",
                weight=0.9,
                reason=f"stored news preference: {topic}",
                confidence=getattr(fact, "confidence", 1.0),
            )
            for topic in topics
        ]


def _is_diagnostic_query(text: str) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in _DIAGNOSTIC_PATTERNS)


def _extract_exclusion(text: str) -> str | None:
    lowered = text.lower()
    for pattern in _NEGATIVE_PATTERNS:
        idx = lowered.find(pattern)
        if idx == -1:
            continue
        topic = text[idx + len(pattern):].strip(" :.-?!\"'")
        return _clean_topic(topic)

    no_match = re.search(r"\bno\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 -]{1,60})", text, re.IGNORECASE)
    if no_match:
        return _clean_topic(no_match.group(1))

    less_match = re.search(r"\bless\s+([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 -]{1,60})", text, re.IGNORECASE)
    if less_match:
        return _clean_topic(less_match.group(1))

    return None


def _clean_topic(text: str) -> str | None:
    topic = re.split(r"\b(?:news|articles|headlines|please|again|from now on)\b", text, maxsplit=1, flags=re.IGNORECASE)[0]
    topic = topic.strip(" :.-?!\"'")
    topic = re.sub(r"^(?:me|about|on|more|any)\s+", "", topic, flags=re.IGNORECASE)
    return topic if topic else None


def _split_topics(value: str) -> list[str]:
    topics = [
        part.strip(" :.-")
        for part in re.split(r"\s*(?:,|;|\||/|\band\b)\s*", value)
    ]
    return [topic for topic in topics if topic]


def _dedupe_terms(terms: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(term)
    return result
