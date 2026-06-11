from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_news.credibility import _prompt_version, run_heuristics, run_llm_scoring, score_article
from ze_news.types import Article, CredibilityFlag, CredibilityReport


def _make_article(title: str = "Test headline", summary: str = "Test summary.") -> Article:
    return Article(
        url="https://example.com/test",
        source_key="test",
        title=title,
        summary=summary,
        published_at=datetime(2026, 6, 7, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Heuristic tests
# ---------------------------------------------------------------------------


def test_betteridge_detected():
    flags = run_heuristics("Is this the end of democracy?", "Experts weigh in.")
    assert any(f.type == "betteridge" for f in flags)


def test_betteridge_question_with_factual_answer_still_flags():
    # Heuristic is purely syntactic; LLM pass would clear this
    flags = run_heuristics("What is the new VAT rate?", "The government announced 23%.")
    assert any(f.type == "betteridge" for f in flags)


def test_betteridge_not_flagged_for_non_question():
    flags = run_heuristics("Government passes new budget", "Finance minister approves plan.")
    assert not any(f.type == "betteridge" for f in flags)


def test_clickbait_detected_en():
    flags = run_heuristics("You won't believe what happened next", "Click to find out.")
    assert any(f.type == "clickbait" for f in flags)


def test_clickbait_detected_pt():
    flags = run_heuristics("Não vai acreditar no que aconteceu", "Veja aqui.")
    assert any(f.type == "clickbait" for f in flags)


def test_vague_attribution_detected():
    flags = run_heuristics(
        "Sources close to the government say new tax is coming",
        "Sources familiar with the situation claim...",
    )
    assert any(f.type == "vague_attribution" for f in flags)


def test_weasel_words_detected():
    flags = run_heuristics(
        "New drug linked to cancer risk",
        "Researchers say the medication could cause side effects.",
    )
    assert any(f.type == "weasel_words" for f in flags)


def test_emotional_manipulation_detected():
    flags = run_heuristics(
        "Catastrophic failure in government",
        "Officials face questions after policy misstep.",
    )
    assert any(f.type == "emotional_manipulation" for f in flags)


def test_sensationalism_detected():
    flags = run_heuristics(
        "Unprecedented earnings miss at tech giant",
        "Company missed analyst estimates by 3%.",
    )
    assert any(f.type == "sensationalism" for f in flags)


def test_clean_article_no_flags():
    flags = run_heuristics(
        "Parliament approves 2026 budget",
        "The budget passed with 187 votes in favour and 105 against.",
    )
    assert flags == []


def test_heuristic_flag_has_detail():
    flags = run_heuristics("Is this the worst government ever?", "")
    betteridge = next(f for f in flags if f.type == "betteridge")
    assert betteridge.detail
    assert betteridge.source == "heuristic"
    assert betteridge.confidence == "high"


def test_betteridge_is_language_agnostic():
    flags = run_heuristics("É este o pior governo de sempre?", "")
    assert any(f.type == "betteridge" and f.lang == "any" for f in flags)


# ---------------------------------------------------------------------------
# CredibilityReport helpers
# ---------------------------------------------------------------------------


def _make_flag(flag_type: str, confidence: str = "high") -> CredibilityFlag:
    return CredibilityFlag(
        type=flag_type,
        label="Test label",
        detail="Test detail",
        source="heuristic",
        confidence=confidence,
    )


def test_high_confidence_flags_property():
    report = CredibilityReport(flags=[
        _make_flag("betteridge", "high"),
        _make_flag("weasel_words", "low"),
    ])
    assert len(report.high_confidence_flags) == 1
    assert report.high_confidence_flags[0].type == "betteridge"


def test_is_briefing_worthy_two_high_confidence():
    report = CredibilityReport(flags=[
        _make_flag("betteridge", "high"),
        _make_flag("clickbait", "high"),
    ])
    assert report.is_briefing_worthy is True


def test_is_briefing_worthy_single_betteridge():
    report = CredibilityReport(flags=[_make_flag("betteridge", "high")])
    assert report.is_briefing_worthy is True


def test_not_briefing_worthy_single_vague_attribution():
    # vague_attribution is high-confidence but not betteridge/clickbait/headline_mismatch
    # — single flag that's not in the special set doesn't pass
    report = CredibilityReport(flags=[_make_flag("vague_attribution", "high")])
    assert report.is_briefing_worthy is False


def test_not_briefing_worthy_only_low_confidence():
    report = CredibilityReport(flags=[
        _make_flag("weasel_words", "low"),
        _make_flag("sensationalism", "low"),
    ])
    assert report.is_briefing_worthy is False


def test_not_briefing_worthy_empty():
    report = CredibilityReport(flags=[])
    assert report.is_briefing_worthy is False


# ---------------------------------------------------------------------------
# LLM scoring
# ---------------------------------------------------------------------------


async def test_run_llm_scoring_present_verdict_adds_flag():
    client = MagicMock()
    response = MagicMock()
    response.content = json.dumps({
        "verdicts": {
            "headline_mismatch": {
                "verdict": "present",
                "detail": "Headline says 'proves' but summary says 'suggests'.",
            }
        },
        "cleared_heuristic_flags": [],
    })
    client.complete = AsyncMock(return_value=response)

    flags = await run_llm_scoring("Headline", "Summary", [], client, "test-model")
    assert any(f.type == "headline_mismatch" and f.source == "llm" for f in flags)


async def test_run_llm_scoring_clears_heuristic_false_positive():
    client = MagicMock()
    response = MagicMock()
    response.content = json.dumps({
        "verdicts": {},
        "cleared_heuristic_flags": ["betteridge"],
    })
    client.complete = AsyncMock(return_value=response)

    heuristic = [_make_flag("betteridge", "high")]
    flags = await run_llm_scoring("What is the VAT rate?", "23%.", heuristic, client, "test-model")
    assert not any(f.type == "betteridge" for f in flags)


async def test_run_llm_scoring_uncertain_not_stored():
    client = MagicMock()
    response = MagicMock()
    response.content = json.dumps({
        "verdicts": {
            "clickbait": {"verdict": "uncertain", "detail": ""},
        },
        "cleared_heuristic_flags": [],
    })
    client.complete = AsyncMock(return_value=response)

    flags = await run_llm_scoring("Some title", "Some summary.", [], client, "test-model")
    assert not any(f.type == "clickbait" for f in flags)


async def test_run_llm_scoring_returns_heuristics_on_error():
    client = MagicMock()
    client.complete = AsyncMock(side_effect=Exception("API error"))

    heuristic = [_make_flag("betteridge", "high")]
    flags = await run_llm_scoring("Title?", "Summary.", heuristic, client, "test-model")
    # Falls back to heuristic flags unchanged
    assert len(flags) == 1
    assert flags[0].type == "betteridge"


# ---------------------------------------------------------------------------
# score_article
# ---------------------------------------------------------------------------


async def test_score_article_heuristic_only():
    client = MagicMock()
    article = _make_article("Is this the worst government ever?", "Some summary.")

    report = await score_article(article, client=client, model="test-model", llm_enabled=False)

    assert report.status == "heuristic_only"
    assert report.model is None
    assert report.analyzed_at is not None
    assert any(f.type == "betteridge" for f in report.flags)
    client.complete.assert_not_called() if hasattr(client, "complete") else None


async def test_score_article_complete():
    client = MagicMock()
    response = MagicMock()
    response.content = json.dumps({
        "verdicts": {
            "betteridge": {"verdict": "absent", "detail": ""},
        },
        "cleared_heuristic_flags": ["betteridge"],
    })
    client.complete = AsyncMock(return_value=response)

    article = _make_article("Is this real?", "Yes, it is.")
    report = await score_article(article, client=client, model="test-model", llm_enabled=True)

    assert report.status == "complete"
    assert report.model == "test-model"
    assert report.prompt_version is not None
    assert len(report.prompt_version) == 12


def test_prompt_version_is_stable():
    v1 = _prompt_version()
    v2 = _prompt_version()
    assert v1 == v2
    assert len(v1) == 12
