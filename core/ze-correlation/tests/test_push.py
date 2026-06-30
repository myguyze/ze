"""Tests for CorrelationPushConsumer and CorrelationJob (Phase 59)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4


from ze_correlation.job import CorrelationJob
from ze_correlation.push import CorrelationPushConsumer
from ze_correlation.types import EvidenceRef, Hypothesis

UTC = timezone.utc


def _make_settings(
    *,
    enabled: bool = True,
    dry_run: bool = False,
    max_seeds_per_run: int = 20,
    seed_lookback_hours: float = 8.0,
    max_pushes_per_day: int = 3,
    tau_push: float = 0.6,
    tau_relevance: float = 0.5,
    novelty_similarity_max: float = 0.85,
) -> MagicMock:
    s = MagicMock()
    s.config = {
        "correlation": {
            "push": {
                "enabled": enabled,
                "dry_run": dry_run,
                "max_seeds_per_run": max_seeds_per_run,
                "seed_lookback_hours": seed_lookback_hours,
                "max_pushes_per_day": max_pushes_per_day,
            },
            "salience": {
                "surfacing": {
                    "tau_push": tau_push,
                    "tau_relevance": tau_relevance,
                    "novelty_similarity_max": novelty_similarity_max,
                },
                "budget": {"max_pushes_per_day": max_pushes_per_day},
            },
        }
    }
    return s


def _make_hypothesis(
    *,
    confidence: float = 0.75,
    relevance: float = 0.65,
    summary: str = "Signal A connects to Signal B",
) -> Hypothesis:
    return Hypothesis(
        id=uuid4(),
        summary=summary,
        narrative="These two events appear related because...",
        relation="pattern",
        confidence=confidence,
        relevance=relevance,
        evidence=[],
        entities=[uuid4()],
        created_at=datetime.now(UTC),
        surfaced=False,
    )


def _make_consumer(
    settings: MagicMock | None = None,
    *,
    seed_ids: list[UUID] | None = None,
    hypotheses: list[Hypothesis] | None = None,
    pushed_count: int = 0,
    recent_summaries: list[str] | None = None,
    embedder: MagicMock | None = None,
    nli_client: MagicMock | None = None,
) -> tuple[CorrelationPushConsumer, dict]:
    if settings is None:
        settings = _make_settings()

    engine = MagicMock()
    engine.correlate = AsyncMock(return_value=hypotheses or [])

    hypothesis_store = MagicMock()
    hypothesis_store.mark_surfaced = AsyncMock()
    hypothesis_store.list_recently_surfaced_summaries = AsyncMock(
        return_value=recent_summaries or []
    )

    memory_store = MagicMock()
    memory_store.list_recent_signal_ids = AsyncMock(return_value=seed_ids or [uuid4(), uuid4()])

    notifier = MagicMock()
    notifier.push = AsyncMock()

    push_log = MagicMock()
    push_log.count_sent_within_hours = AsyncMock(return_value=pushed_count)
    push_log.log = AsyncMock()

    if nli_client is None:
        nli_client = AsyncMock()
        nli_client.scores = AsyncMock(return_value=[])
        nli_client.grounding_score = MagicMock(return_value=1.0)

    consumer = CorrelationPushConsumer(
        engine=engine,
        hypothesis_store=hypothesis_store,
        memory_store=memory_store,
        notifier=notifier,
        push_log=push_log,
        settings=settings,
        embedder=embedder,
        nli_client=nli_client,
    )
    mocks = {
        "engine": engine,
        "hypothesis_store": hypothesis_store,
        "memory_store": memory_store,
        "notifier": notifier,
        "push_log": push_log,
    }
    return consumer, mocks


# ── seed selection ────────────────────────────────────────────────────────────

async def test_seed_selection_respects_max_seeds_per_run():
    settings = _make_settings(max_seeds_per_run=5)
    consumer, mocks = _make_consumer(settings)
    await consumer.run_once()
    _, call_kwargs = mocks["memory_store"].list_recent_signal_ids.call_args
    limit_arg = mocks["memory_store"].list_recent_signal_ids.call_args[0][1]
    assert limit_arg == 5


async def test_seed_selection_uses_lookback_window():
    settings = _make_settings(seed_lookback_hours=4.0)
    consumer, mocks = _make_consumer(settings)
    await consumer.run_once()
    since_arg = mocks["memory_store"].list_recent_signal_ids.call_args[0][0]
    # since should be approximately 4 hours ago
    delta = datetime.now(UTC) - since_arg
    assert abs(delta.total_seconds() - 4 * 3600) < 5


async def test_explicit_seeds_skip_memory_query():
    consumer, mocks = _make_consumer()
    seeds = [uuid4(), uuid4()]
    await consumer.run_once(seeds=seeds)
    mocks["memory_store"].list_recent_signal_ids.assert_not_called()
    mocks["engine"].correlate.assert_awaited_once_with(seeds, mode="proactive")


async def test_no_seeds_returns_early():
    consumer, mocks = _make_consumer(seed_ids=[])
    mocks["memory_store"].list_recent_signal_ids = AsyncMock(return_value=[])
    result = await consumer.run_once()
    assert result == []
    mocks["engine"].correlate.assert_not_awaited()


# ── push bar ──────────────────────────────────────────────────────────────────

async def test_qualifying_hypothesis_is_pushed():
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h])
    await consumer.run_once()
    mocks["notifier"].push.assert_awaited_once()
    mocks["hypothesis_store"].mark_surfaced.assert_awaited_once_with(h.id)
    mocks["push_log"].log.assert_awaited_once()


async def test_low_confidence_rejected():
    h = _make_hypothesis(confidence=0.4, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h])
    await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()
    mocks["hypothesis_store"].mark_surfaced.assert_not_awaited()


async def test_low_relevance_rejected():
    h = _make_hypothesis(confidence=0.75, relevance=0.2)
    consumer, mocks = _make_consumer(hypotheses=[h])
    await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()


async def test_budget_exceeded_rejects_push():
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h], pushed_count=3)
    await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()


async def test_novelty_too_similar_rejected():
    import numpy as np

    embedder = MagicMock()
    vec = np.array([1.0, 0.0, 0.0])
    embedder.encode = MagicMock(return_value=vec)

    h = _make_hypothesis(confidence=0.75, relevance=0.65, summary="A connects to B")
    consumer, mocks = _make_consumer(
        hypotheses=[h],
        recent_summaries=["A connects to B almost identically"],
        embedder=embedder,
    )
    await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()


async def test_novelty_no_embedder_skips_check():
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h], embedder=None)
    await consumer.run_once()
    mocks["notifier"].push.assert_awaited_once()


async def test_low_grounding_rejected():
    nli = AsyncMock()
    nli.scores = AsyncMock(
        return_value=[{"contradiction": 0.5, "neutral": 0.4, "entailment": 0.1}]
    )
    nli.grounding_score = MagicMock(return_value=0.1)
    evidence = [
        EvidenceRef(
            kind="signal",
            id=uuid4(),
            label="Stock market moved sharply",
            external_ref=None,
            origin="graph_recall",
            retrieved_at=datetime.now(UTC),
        )
    ]
    h = Hypothesis(
        id=uuid4(),
        summary="User's coffee preference changed",
        narrative="Possible link",
        relation="pattern",
        confidence=0.75,
        relevance=0.65,
        evidence=evidence,
        entities=[uuid4()],
        created_at=datetime.now(UTC),
    )
    settings = _make_settings()
    settings.config["memory"] = {"nli_grounding_threshold": 0.30}
    consumer, mocks = _make_consumer(settings, hypotheses=[h], nli_client=nli)
    await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()


# ── surfaced flag ─────────────────────────────────────────────────────────────

async def test_pushed_hypothesis_marked_surfaced():
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h])
    await consumer.run_once()
    mocks["hypothesis_store"].mark_surfaced.assert_awaited_once_with(h.id)


async def test_sub_bar_hypothesis_not_marked_surfaced():
    h = _make_hypothesis(confidence=0.3, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h])
    await consumer.run_once()
    mocks["hypothesis_store"].mark_surfaced.assert_not_awaited()


# ── dry_run ───────────────────────────────────────────────────────────────────

async def test_dry_run_does_not_push():
    settings = _make_settings(dry_run=True)
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(settings, hypotheses=[h])
    result = await consumer.run_once()
    mocks["notifier"].push.assert_not_awaited()
    mocks["hypothesis_store"].mark_surfaced.assert_not_awaited()
    assert len(result) == 1


async def test_dry_run_does_not_log_to_push_log():
    settings = _make_settings(dry_run=True)
    h = _make_hypothesis(confidence=0.75, relevance=0.65)
    consumer, mocks = _make_consumer(settings, hypotheses=[h])
    await consumer.run_once()
    mocks["push_log"].log.assert_not_awaited()


# ── disabled ──────────────────────────────────────────────────────────────────

async def test_disabled_with_no_dry_run_returns_early():
    settings = _make_settings(enabled=False, dry_run=False)
    consumer, mocks = _make_consumer(settings)
    result = await consumer.run_once()
    assert result == []
    mocks["engine"].correlate.assert_not_awaited()


# ── return value ──────────────────────────────────────────────────────────────

async def test_returns_all_hypotheses_not_just_pushed():
    h_good = _make_hypothesis(confidence=0.75, relevance=0.65)
    h_bad = _make_hypothesis(confidence=0.3, relevance=0.65)
    consumer, mocks = _make_consumer(hypotheses=[h_good, h_bad])
    result = await consumer.run_once()
    assert len(result) == 2
    mocks["notifier"].push.assert_awaited_once()


# ── CorrelationJob ────────────────────────────────────────────────────────────

async def test_correlation_job_delegates_to_consumer():
    consumer = MagicMock()
    consumer.run_once = AsyncMock(return_value=[])
    job = CorrelationJob(push_consumer=consumer)
    assert job.job_id == "correlation_scan"
    await job.run()
    consumer.run_once.assert_awaited_once()
