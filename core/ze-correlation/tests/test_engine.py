"""Tests for CorrelationEngine (Phase 57).

All I/O is mocked: no real DB, no real LLM, no real relevance model.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4


from ze_correlation.engine import CorrelationEngine
from ze_correlation.store import PostgresHypothesisStore
from ze_correlation.types import Hypothesis

UTC = timezone.utc


# ── fixtures ──────────────────────────────────────────────────────────────────


def _make_settings(**engine_overrides: object) -> MagicMock:
    engine_cfg = {
        "max_hops_inline": 1,
        "max_hops_proactive": 2,
        "neighbourhood_limit_inline": 15,
        "neighbourhood_limit_proactive": 30,
        "max_seeds_inline": 5,
        "timeout_seconds_inline": 5.0,
        "model": "anthropic/claude-haiku-4-5",
        **engine_overrides,
    }
    s = MagicMock()
    s.config = {"correlation": {"engine": engine_cfg}}
    return s


def _make_expansion(
    *,
    signal_ids: list[UUID] | None = None,
    fact_ids: list[UUID] | None = None,
    episode_ids: list[UUID] | None = None,
) -> MagicMock:
    exp = MagicMock()
    exp.signal_ids = signal_ids or []
    exp.fact_ids = fact_ids or []
    exp.episode_ids = episode_ids or []
    exp.entity_ids = []
    exp.procedure_ids = []
    exp.relationships = []
    exp.is_empty.return_value = not (signal_ids or fact_ids or episode_ids)
    return exp


def _make_signal(
    sig_id: UUID | None = None,
    title: str = "Test Signal",
    source: str = "news",
    occurred_at: datetime | None = None,
) -> tuple[MagicMock, datetime]:
    sig = MagicMock()
    sig.id = sig_id or uuid4()
    sig.source = source
    sig.external_ref = f"https://example.com/{sig.id}"
    sig.title = title
    sig.summary = f"Summary of {title}"
    sig.occurred_at = occurred_at or datetime(2024, 6, 12, tzinfo=UTC)
    sig.magnitude = 0.7
    sig.payload = {}
    sig.expires_at = None
    ingested_at = datetime(2024, 6, 12, 10, 0, tzinfo=UTC)
    return sig, ingested_at


def _make_llm_response(
    summary: str = "Potential connection found",
    narrative: str = "There appears to be a connection based on shared entities.",
    relation: str = "tension",
    confidence: float = 0.75,
    evidence_ids: list[str] | None = None,
    no_connection: bool = False,
) -> str:
    if no_connection:
        return json.dumps({"no_connection": True})
    return json.dumps(
        {
            "summary": summary,
            "narrative": narrative,
            "relation": relation,
            "confidence": confidence,
            "evidence_ids": evidence_ids or [],
        }
    )


def _make_engine(
    *,
    expansion: MagicMock | None = None,
    signals: list[tuple] | None = None,
    facts: list | None = None,
    episodes: list | None = None,
    llm_response: str | None = None,
    settings: MagicMock | None = None,
    entity_names: list[str] | None = None,
) -> tuple[CorrelationEngine, MagicMock, MagicMock]:
    settings = settings or _make_settings()

    graph_store = MagicMock()
    graph_store.expand = AsyncMock(return_value=expansion or _make_expansion())

    memory_store = MagicMock()
    memory_store.graph_store = graph_store
    memory_store.get_entities_by_ids = AsyncMock(
        return_value=[
            MagicMock(canonical_name=n) for n in (entity_names or ["TestEntity"])
        ]
    )
    memory_store.get_facts_by_ids = AsyncMock(return_value=facts or [])
    memory_store.get_episodes_by_ids = AsyncMock(return_value=episodes or [])
    memory_store.get_signals_by_ids = AsyncMock(return_value=signals or [])
    memory_store.pin_signals = AsyncMock()

    relevance_model = MagicMock()
    rset = MagicMock()
    relevance_model.build = AsyncMock(return_value=rset)
    score_obj = MagicMock()
    score_obj.value = 0.8
    relevance_model.score = MagicMock(return_value=score_obj)

    llm_client = MagicMock()
    llm_client.complete = AsyncMock(return_value=llm_response or _make_llm_response())

    hyp_store = MagicMock(spec=PostgresHypothesisStore)
    hyp_store.save = AsyncMock()

    engine = CorrelationEngine(
        memory_store=memory_store,
        relevance_model=relevance_model,
        llm_client=llm_client,
        hypothesis_store=hyp_store,
        settings=settings,
    )
    return engine, memory_store, hyp_store


# ── tests ─────────────────────────────────────────────────────────────────────


async def test_neighbourhood_expansion_uses_prior_signal():
    """Neighbourhood expansion must reach a previously ingested prior signal sharing an entity.

    The prior signal is NOT in the seeds — it must be discovered via graph expansion.
    """
    entity_id = uuid4()
    prior_signal_id = uuid4()
    current_signal_id = uuid4()

    prior_sig, ingested_at = _make_signal(prior_signal_id, title="Pentagon ban (Jun 1)")
    current_sig, _ = _make_signal(current_signal_id, title="Fable 5 ban (Jun 12)")

    expansion = _make_expansion(signal_ids=[prior_signal_id, current_signal_id])
    llm_resp = _make_llm_response(
        summary="Pattern: two bans linked to same entity",
        relation="tension",
        evidence_ids=[str(prior_signal_id), str(current_signal_id)],
    )

    engine, memory_store, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(prior_sig, ingested_at), (current_sig, ingested_at)],
        llm_response=llm_resp,
        entity_names=["TestEntity"],
    )

    results = await engine.correlate([entity_id], mode="inline")

    assert len(results) == 1
    assert isinstance(results[0], Hypothesis)
    # Both signals cited as evidence
    assert len(results[0].evidence) == 2
    cited = {str(e.id) for e in results[0].evidence}
    assert str(prior_signal_id) in cited
    assert str(current_signal_id) in cited
    # Graph expansion was called with the seed
    memory_store.graph_store.expand.assert_called_once()
    call_args = memory_store.graph_store.expand.call_args
    assert entity_id in call_args[0][0]


async def test_hallucinated_id_rejected():
    """Hypothesis is not formed when the LLM cites an id not in the neighbourhood."""
    sig_id = uuid4()
    hallucinated_id = uuid4()  # not in neighbourhood

    sig, ingested_at = _make_signal(sig_id)
    expansion = _make_expansion(signal_ids=[sig_id])
    llm_resp = _make_llm_response(
        evidence_ids=[
            str(sig_id),
            str(hallucinated_id),
        ],  # hallucinated_id not in neighbourhood
    )

    engine, _, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at)],
        llm_response=llm_resp,
    )

    results = await engine.correlate([uuid4()], mode="inline")

    assert results == []
    hyp_store.save.assert_not_called()


async def test_no_web_search_tool_in_correlation_call():
    """The LLM correlation call must use complete(), not complete_with_tools()."""
    sig_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2_id = uuid4()
    sig2, ingested_at2 = _make_signal(sig2_id, title="Signal 2")
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id), str(sig2_id)])

    engine, memory_store, _ = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at2)],
        llm_response=llm_resp,
    )

    await engine.correlate([uuid4()], mode="inline")

    # complete() must have been called
    memory_store.get_signals_by_ids.return_value  # just access to not raise
    llm_client = engine._llm
    llm_client.complete.assert_called_once()
    # complete_with_tools must NOT have been called
    assert (
        not hasattr(llm_client, "complete_with_tools")
        or not llm_client.complete_with_tools.called
    )


async def test_all_cited_evidence_tagged_graph_recall():
    """Every evidence item in the correlation call must have origin='graph_recall'."""
    sig_id = uuid4()
    sig2_id = uuid4()
    sig, ingested_at = _make_signal(sig_id, title="Signal A")
    sig2, ingested_at2 = _make_signal(sig2_id, title="Signal B")
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id), str(sig2_id)])

    engine, _, _ = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at2)],
        llm_response=llm_resp,
    )

    results = await engine.correlate([uuid4()], mode="inline")

    assert len(results) == 1
    for ev in results[0].evidence:
        assert ev.origin == "graph_recall", f"Expected graph_recall, got {ev.origin}"


async def test_recall_guarantee_fewer_than_two_items():
    """Hypothesis must NOT be formed when fewer than 2 evidence items are cited."""
    sig_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    expansion = _make_expansion(signal_ids=[sig_id])
    # LLM cites only one item
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id)])

    engine, _, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at)],
        llm_response=llm_resp,
    )

    results = await engine.correlate([uuid4()], mode="inline")

    assert results == []
    hyp_store.save.assert_not_called()


async def test_no_connection_output_produces_no_hypothesis():
    """When the LLM says no_connection, no hypothesis is formed."""
    sig_id = uuid4()
    sig2_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2, _ = _make_signal(sig2_id)
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(no_connection=True)

    engine, _, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at)],
        llm_response=llm_resp,
    )

    results = await engine.correlate([uuid4()], mode="inline")

    assert results == []
    hyp_store.save.assert_not_called()


async def test_inline_uses_tighter_bounds_than_proactive():
    """correlate(mode='inline') must use tighter hop/limit bounds than mode='proactive'."""
    settings = _make_settings(
        max_hops_inline=1,
        max_hops_proactive=2,
        neighbourhood_limit_inline=15,
        neighbourhood_limit_proactive=30,
    )

    sig_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2_id = uuid4()
    sig2, _ = _make_signal(sig2_id)
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id), str(sig2_id)])

    engine, memory_store, _ = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at)],
        llm_response=llm_resp,
        settings=settings,
    )

    seed = uuid4()

    # inline call
    memory_store.graph_store.expand.reset_mock()
    await engine.correlate([seed], mode="inline")
    inline_call = memory_store.graph_store.expand.call_args
    assert inline_call.kwargs["max_hops"] == 1
    assert inline_call.kwargs["limit"] == 15

    # proactive call — reset expansion to avoid empty-neighbourhood short-circuit
    memory_store.graph_store.expand.reset_mock()
    memory_store.graph_store.expand.return_value = expansion
    await engine.correlate([seed], mode="proactive")
    proactive_call = memory_store.graph_store.expand.call_args
    assert proactive_call.kwargs["max_hops"] == 2
    assert proactive_call.kwargs["limit"] == 30


async def test_golden_fable5_pentagon_scenario():
    """Golden replay: Pentagon event pre-seeded in graph; only Fable 5 signal fed at runtime.

    The engine must recall the Pentagon event and yield a tension/causal_guess hypothesis.
    """
    # The entity shared between both signals (e.g., a game publisher entity)
    entity_id = uuid4()

    # Pentagon event — pre-ingested in the graph, NOT in seeds
    pentagon_signal_id = uuid4()
    pentagon_sig, pentagon_ingested = _make_signal(
        pentagon_signal_id,
        title="Pentagon ban on publisher (Jun 1)",
        source="news",
        occurred_at=datetime(2024, 6, 1, tzinfo=UTC),
    )

    # Fable 5 signal — the current signal triggering correlation
    fable_signal_id = uuid4()
    fable_sig, fable_ingested = _make_signal(
        fable_signal_id,
        title="Fable 5 ban (Jun 12)",
        source="news",
        occurred_at=datetime(2024, 6, 12, tzinfo=UTC),
    )

    # Graph expansion from the Fable 5 entity finds the Pentagon signal
    expansion = _make_expansion(signal_ids=[pentagon_signal_id, fable_signal_id])

    llm_resp = _make_llm_response(
        summary="Pentagon ban may be linked to the same publisher behind Fable 5",
        narrative=(
            "The Pentagon ban [pentagon] and the Fable 5 ban [fable] share a common entity. "
            "This could be coincidental, but the timing raises the possibility of a broader "
            "regulatory pattern. Confidence is moderate — direct causation is unconfirmed."
        ),
        relation="tension",
        confidence=0.72,
        evidence_ids=[str(pentagon_signal_id), str(fable_signal_id)],
    )

    engine, memory_store, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(pentagon_sig, pentagon_ingested), (fable_sig, fable_ingested)],
        llm_response=llm_resp,
        entity_names=["PublisherCo"],
    )

    # Only the Fable 5 entity is the seed — Pentagon must be recalled via graph
    results = await engine.correlate([entity_id], mode="inline")

    assert len(results) == 1
    hyp = results[0]

    # Correct relation type
    assert hyp.relation in {"tension", "causal_guess"}
    # Both signals cited
    cited = {str(e.id) for e in hyp.evidence}
    assert str(pentagon_signal_id) in cited, "Pentagon signal must be in evidence"
    assert str(fable_signal_id) in cited, "Fable 5 signal must be in evidence"
    # All evidence is graph_recall
    for ev in hyp.evidence:
        assert ev.origin == "graph_recall"
    # Pentagon's ingested_at reflects when it entered memory
    pentagon_ev = next(e for e in hyp.evidence if e.id == pentagon_signal_id)
    assert pentagon_ev.ingested_at == pentagon_ingested
    # Hypothesis persisted
    hyp_store.save.assert_called_once_with(hyp)
    # Signals pinned
    memory_store.pin_signals.assert_called_once()


async def test_empty_neighbourhood_produces_no_hypothesis():
    """Engine returns [] when graph expansion is empty."""
    expansion = _make_expansion()  # is_empty=True

    engine, _, hyp_store = _make_engine(expansion=expansion)

    results = await engine.correlate([uuid4()], mode="inline")

    assert results == []
    hyp_store.save.assert_not_called()


async def test_inline_timeout_drops_silently():
    """Inline correlation drops silently when the LLM exceeds timeout_seconds_inline."""
    import asyncio

    sig_id = uuid4()
    sig2_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2, _ = _make_signal(sig2_id)
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])

    engine, memory_store, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at)],
        settings=_make_settings(timeout_seconds_inline=0.001),
    )

    async def _slow_complete(**_kwargs):  # type: ignore[return]
        await asyncio.sleep(10)

    engine._llm.complete = AsyncMock(side_effect=_slow_complete)

    results = await engine.correlate([uuid4()], mode="inline")

    assert results == []
    hyp_store.save.assert_not_called()


async def test_signal_pinning_called_for_cited_signals():
    """Cited signals must be pinned after a hypothesis is formed."""
    sig_id = uuid4()
    sig2_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2, _ = _make_signal(sig2_id)
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id), str(sig2_id)])

    engine, memory_store, _ = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at)],
        llm_response=llm_resp,
    )

    await engine.correlate([uuid4()], mode="inline")

    memory_store.pin_signals.assert_called_once()
    pinned_ids = memory_store.pin_signals.call_args[0][0]
    assert set(pinned_ids) == {sig_id, sig2_id}


async def test_max_seeds_trimmed_for_inline():
    """When more than max_seeds_inline seeds are given for inline mode, only top-N are used."""
    settings = _make_settings(max_seeds_inline=2)

    seeds = [uuid4() for _ in range(5)]
    sig_id = uuid4()
    sig2_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    sig2, _ = _make_signal(sig2_id)
    expansion = _make_expansion(signal_ids=[sig_id, sig2_id])
    llm_resp = _make_llm_response(evidence_ids=[str(sig_id), str(sig2_id)])

    engine, memory_store, _ = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at), (sig2, ingested_at)],
        llm_response=llm_resp,
        entity_names=["E1", "E2"],
        settings=settings,
    )

    await engine.correlate(seeds, mode="inline")

    expand_call = memory_store.graph_store.expand.call_args
    # At most max_seeds_inline seeds were passed to expand
    passed_seeds = expand_call[0][0]
    assert len(passed_seeds) <= 2


async def test_proactive_prefilter_drops_low_relevance():
    """Proactive correlation is skipped when relevance score is below threshold."""
    sig_id = uuid4()
    sig, ingested_at = _make_signal(sig_id)
    expansion = _make_expansion(signal_ids=[sig_id])

    engine, _, hyp_store = _make_engine(
        expansion=expansion,
        signals=[(sig, ingested_at)],
    )
    # Override relevance model to return low score
    low_score = MagicMock()
    low_score.value = 0.1
    engine._relevance.score = MagicMock(return_value=low_score)

    results = await engine.correlate([uuid4()], mode="proactive")

    assert results == []
    hyp_store.save.assert_not_called()
