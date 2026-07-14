"""Tests for memory-chunk trace extraction (phase 106, User Story 1)."""

from __future__ import annotations

from types import SimpleNamespace

from ze_core.orchestration.nodes.trace import _extract_memory_chunks, record_trace


def _fact(relevance_score=None, confidence=1.0):
    return SimpleNamespace(
        predicate="likes", value="coffee", relevance_score=relevance_score, confidence=confidence
    )


def _episode(relevance_score=None):
    return SimpleNamespace(summary="a chat", response="hi", relevance_score=relevance_score)


def test_extract_memory_chunks_sets_score_from_relevance_score_not_confidence():
    ctx = SimpleNamespace(facts=[_fact(relevance_score=0.82, confidence=1.0)], episodes=[])
    chunks = _extract_memory_chunks(ctx)
    assert len(chunks) == 1
    assert chunks[0].score == 0.82
    assert chunks[0].extraction_confidence == 1.0


def test_extract_memory_chunks_extraction_confidence_kept_separate_from_score():
    ctx = SimpleNamespace(
        facts=[_fact(relevance_score=0.1, confidence=0.99)], episodes=[]
    )
    chunks = _extract_memory_chunks(ctx)
    assert chunks[0].score == 0.1
    assert chunks[0].extraction_confidence == 0.99
    assert chunks[0].score != chunks[0].extraction_confidence


def test_extract_memory_chunks_missing_relevance_score_defaults_to_zero():
    ctx = SimpleNamespace(facts=[_fact(relevance_score=None)], episodes=[])
    chunks = _extract_memory_chunks(ctx)
    assert chunks[0].score == 0.0


def test_extract_memory_chunks_episode_score_from_relevance_score():
    ctx = SimpleNamespace(facts=[], episodes=[_episode(relevance_score=0.55)])
    chunks = _extract_memory_chunks(ctx)
    assert chunks[0].score == 0.55
    assert chunks[0].source == "episode"


def test_extract_memory_chunks_empty_context_returns_empty_list():
    ctx = SimpleNamespace(facts=[], episodes=[])
    assert _extract_memory_chunks(ctx) == []


def test_extract_memory_chunks_none_context_returns_empty_list():
    assert _extract_memory_chunks(None) == []


async def test_record_trace_produces_empty_memory_chunks_not_missing_trace():
    envelope = SimpleNamespace(
        primary_agent="companion",
        routing_method="embedding",
        confidence=0.9,
        score_gap=0.1,
        is_compound=False,
        subtasks=[],
    )
    state = {
        "envelope": envelope,
        "agent_result": None,
        "memory_context": SimpleNamespace(facts=[], episodes=[]),
    }

    result = await record_trace(state, config={})

    trace = result["message_trace"]
    assert trace is not None
    assert trace.memory_chunks == []
