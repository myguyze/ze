"""Composite candidate scoring — similarity * recency-decay * confidence (User Story 3).

Orders retrieval candidates before token budgeting so the best memories (not
just the raw ANN nearest neighbours) win the budget (FR-010/FR-011/FR-012).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from ze_logging import get_logger
from ze_memory.relevance_config import CompositeWeights

log = get_logger(__name__)

# Half-life for exponential recency decay. Tuning constant, not fixed by spec.
_RECENCY_HALF_LIFE_DAYS = 30.0
_NEUTRAL_RECENCY = 0.5

# Priority order of timestamp-like fields to use as the recency signal, checked
# across both raw asyncpg rows (dict-like) and projected dataclasses (attrs).
_RECENCY_FIELDS = ("updated_at", "last_turn_at", "created_at", "start_at", "occurred_at")


def _get(candidate: Any, *keys: str) -> Any:
    for key in keys:
        value = candidate.get(key) if hasattr(candidate, "get") else getattr(candidate, key, None)
        if value is not None:
            return value
    return None


def _similarity_component(candidate: Any) -> float:
    sim = _get(candidate, "similarity", "relevance_score")
    return float(sim) if sim is not None else 0.0


def _confidence_component(candidate: Any) -> float:
    conf = _get(candidate, "confidence")
    return float(conf) if conf is not None else 1.0


def recency_decay(timestamp: datetime | None, now: datetime) -> float:
    """Exponential recency decay in [0, 1]. A missing timestamp gets a neutral score."""
    if timestamp is None:
        return _NEUTRAL_RECENCY
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - timestamp).total_seconds() / 86400)
    return math.pow(0.5, age_days / _RECENCY_HALF_LIFE_DAYS)


def _recency_component(candidate: Any, now: datetime) -> float:
    ts = _get(candidate, *_RECENCY_FIELDS)
    return recency_decay(ts, now)


def composite_score(candidate: Any, weights: CompositeWeights, now: datetime) -> float:
    """similarity * w.similarity + recency_decay(age) * w.recency + confidence * w.confidence.

    Pure function — no I/O, never raises. Works on raw asyncpg rows (dict-like,
    pre-projection — "similarity" key) and on projected Fact/Episode/Entity/Event
    dataclasses ("relevance_score" attribute) uniformly. A missing similarity
    contributes 0.0; a missing recency timestamp contributes a neutral 0.5, so
    candidates the schema has no timestamp for (e.g. entities) aren't penalized.
    """
    similarity = _similarity_component(candidate)
    confidence = _confidence_component(candidate)
    recency = _recency_component(candidate, now)

    score = (
        similarity * weights.similarity
        + recency * weights.recency
        + confidence * weights.confidence
    )
    log.debug(
        "composite_score_components",
        similarity=similarity,
        recency=recency,
        confidence=confidence,
        score=score,
    )
    return score


def sort_by_composite_score(
    rows: list[Any], weights: CompositeWeights, now: datetime
) -> list[Any]:
    """Stable-sort candidates by composite_score, highest first."""
    return sorted(rows, key=lambda row: composite_score(row, weights, now), reverse=True)
