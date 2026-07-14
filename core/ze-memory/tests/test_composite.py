"""Tests for composite candidate scoring (User Story 3, phase 106)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ze_memory.composite import composite_score, sort_by_composite_score
from ze_memory.relevance_config import CompositeWeights


NOW = datetime(2026, 7, 14, tzinfo=timezone.utc)


def _row(similarity, confidence=1.0, updated_at=None):
    return {"similarity": similarity, "confidence": confidence, "updated_at": updated_at}


# ── T033: favors recency when similarity comparable; favors confidence similarly ─


def test_composite_score_favors_recency_when_similarity_comparable():
    weights = CompositeWeights(similarity=0.6, recency=0.25, confidence=0.15)
    recent = _row(0.5, confidence=0.5, updated_at=NOW - timedelta(days=1))
    old = _row(0.5, confidence=0.5, updated_at=NOW - timedelta(days=365))

    assert composite_score(recent, weights, NOW) > composite_score(old, weights, NOW)


def test_composite_score_favors_confidence_when_similarity_and_recency_comparable():
    weights = CompositeWeights(similarity=0.6, recency=0.25, confidence=0.15)
    same_ts = NOW - timedelta(days=10)
    high_conf = _row(0.5, confidence=0.95, updated_at=same_ts)
    low_conf = _row(0.5, confidence=0.1, updated_at=same_ts)

    assert composite_score(high_conf, weights, NOW) > composite_score(low_conf, weights, NOW)


def test_composite_score_old_low_confidence_loses_to_recent_high_confidence_at_similar_similarity():
    """The canonical US3 scenario from quickstart.md Story 3."""
    weights = CompositeWeights(similarity=0.6, recency=0.25, confidence=0.15)
    old_low_confidence_marginally_nearer = _row(
        0.81, confidence=0.4, updated_at=NOW - timedelta(days=200)
    )
    recent_high_confidence = _row(0.79, confidence=0.98, updated_at=NOW - timedelta(days=1))

    assert composite_score(recent_high_confidence, weights, NOW) > composite_score(
        old_low_confidence_marginally_nearer, weights, NOW
    )


# ── T034: composite ordering is deterministic / reproducible from stored components


def test_sort_by_composite_score_is_deterministic():
    weights = CompositeWeights(similarity=0.6, recency=0.25, confidence=0.15)
    rows = [
        _row(0.9, confidence=0.5, updated_at=NOW - timedelta(days=100)),
        _row(0.4, confidence=0.9, updated_at=NOW - timedelta(days=1)),
        _row(0.6, confidence=0.6, updated_at=NOW - timedelta(days=10)),
    ]
    first_pass = sort_by_composite_score(rows, weights, NOW)
    second_pass = sort_by_composite_score(list(reversed(rows)), weights, NOW)
    assert first_pass == second_pass


def test_composite_score_reproducible_from_same_components():
    weights = CompositeWeights(similarity=0.6, recency=0.25, confidence=0.15)
    row = _row(0.7, confidence=0.8, updated_at=NOW - timedelta(days=5))
    assert composite_score(row, weights, NOW) == composite_score(row, weights, NOW)


# ── T035: zeroed composite weights reproduce pure-relevance ordering (FR-017) ──


def test_zeroed_recency_and_confidence_weights_reproduce_pure_similarity_ordering():
    weights = CompositeWeights(similarity=1.0, recency=0.0, confidence=0.0)
    rows = [
        _row(0.2, confidence=0.99, updated_at=NOW),
        _row(0.9, confidence=0.1, updated_at=NOW - timedelta(days=1000)),
        _row(0.5, confidence=0.5, updated_at=NOW - timedelta(days=500)),
    ]
    ordered = sort_by_composite_score(rows, weights, NOW)
    assert [r["similarity"] for r in ordered] == [0.9, 0.5, 0.2]


def test_missing_relevance_score_contributes_zero_similarity():
    weights = CompositeWeights(similarity=1.0, recency=0.0, confidence=0.0)
    row = {"similarity": None, "confidence": 1.0}
    assert composite_score(row, weights, NOW) == 0.0


def test_missing_recency_timestamp_uses_neutral_value_not_penalized_to_zero():
    weights = CompositeWeights(similarity=0.0, recency=1.0, confidence=0.0)
    row = {"similarity": 1.0, "confidence": 1.0}
    score = composite_score(row, weights, NOW)
    assert 0.0 < score < 1.0
