from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from ze_core.logging import get_logger
from ze_news.types import (
    AnalysisStatus,
    CredibilityFlag,
    CredibilityReport,
    FLAG_CONFIDENCE,
)

if TYPE_CHECKING:
    from ze_core.openrouter.client import OpenRouterClient
    from ze_news.types import Article

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Heuristic phrase lists
# ---------------------------------------------------------------------------

BETTERIDGE_RE = re.compile(r"\?\s*$")

_CLICKBAIT_EN = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"you won't believe",
        r"will shock you",
        r"doesn't? want you to know",
        r"the truth about",
        r"here's why",
        r"find out why",
        r"this is what happens",
        r"\d+ reasons? (?:why|to|that)",
        r"and it(?:'s| is) worse than you think",
        r"what happened next",
        r"changed everything",
        r"you need to see this",
        r"this will change your",
    ]
]

_CLICKBAIT_PT = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"não vai acreditar",
        r"vai chocar",
        r"a verdade sobre",
        r"descubra porquê",
        r"isto vai mudar tudo",
    ]
]

_WEASEL_EN = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\blinked to\b",
        r"\braises? concerns?\b",
        r"\bquestions? remain\b",
        r"\bsources? (?:say|claim|suggest)\b",
        r"\bsome experts?\b",
        r"\baccording to reports?\b",
        r"\ballegedly\b",
        r"\breportedly\b",
        r"\bcould (?:be|lead|cause|result)\b",
    ]
]

_WEASEL_PT = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\balegadamente\b",
        r"\bpode causar\b",
        r"\bligado a\b",
        r"\blevanta questões\b",
        r"\bfontes dizem\b",
        r"\bsegundo fontes\b",
    ]
]

_VAGUE_ATTR_EN = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bsources? close to\b",
        r"\binsiders? (?:say|claim|suggest)\b",
        r"\bsome experts? (?:say|believe|suggest)\b",
        r"\baccording to reports?\b",
        r"\bit is claimed\b",
        r"\bit has emerged\b",
        r"\bsources? familiar with\b",
    ]
]

_VAGUE_ATTR_PT = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bfontes dizem\b",
        r"\bsegundo fontes\b",
        r"\balegam fontes próximas\b",
    ]
]

_EMOTIONAL_EN = [
    re.compile(r"\b" + w + r"\b", re.IGNORECASE)
    for w in [
        "catastrophic", "devastating", "terrifying", "horrifying",
        "outrageous", "disgusting", "shameful", "unforgivable",
    ]
]

_SENSATIONALISM_EN = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bunprecedented\b",
        r"\bfirst time in history\b",
        r"\bworst ever\b",
        r"\bbiggest ever\b",
        r"\bmost (?:\w+ )?in history\b",
    ]
]

# Descriptive labels used in display
_LABELS: dict[str, str] = {
    "betteridge": "Question headline",
    "clickbait": "Engagement hook language",
    "vague_attribution": "Sources unnamed",
    "headline_mismatch": "Headline stronger than summary",
    "weasel_words": "Hedged claim language",
    "emotional_manipulation": "Heightened emotional language",
    "passive_agency": "Actor not named",
    "false_balance": "Unequal positions presented equally",
    "missing_context": "Context may be incomplete",
    "sensationalism": "Disproportionate framing",
}


# ---------------------------------------------------------------------------
# Heuristic pre-pass
# ---------------------------------------------------------------------------


def run_heuristics(title: str, summary: str) -> list[CredibilityFlag]:
    """Fast, zero-cost pre-pass. High-precision, not high-recall."""
    flags: list[CredibilityFlag] = []
    text = title + " " + summary

    # betteridge — language-agnostic
    if BETTERIDGE_RE.search(title.strip()):
        flags.append(CredibilityFlag(
            type="betteridge",
            label=_LABELS["betteridge"],
            detail="Headline ends with '?' — implies a claim the author won't assert as fact.",
            source="heuristic",
            confidence=FLAG_CONFIDENCE["betteridge"],
            lang="any",
        ))

    # clickbait
    for pattern in _CLICKBAIT_EN:
        m = pattern.search(text)
        if m:
            flags.append(CredibilityFlag(
                type="clickbait",
                label=_LABELS["clickbait"],
                detail=f"Matched phrase: \"{m.group(0)}\"",
                source="heuristic",
                confidence=FLAG_CONFIDENCE["clickbait"],
                lang="en",
            ))
            break
    else:
        for pattern in _CLICKBAIT_PT:
            m = pattern.search(text)
            if m:
                flags.append(CredibilityFlag(
                    type="clickbait",
                    label=_LABELS["clickbait"],
                    detail=f"Matched phrase: \"{m.group(0)}\"",
                    source="heuristic",
                    confidence=FLAG_CONFIDENCE["clickbait"],
                    lang="pt",
                ))
                break

    # vague_attribution
    for pattern in _VAGUE_ATTR_EN:
        m = pattern.search(text)
        if m:
            flags.append(CredibilityFlag(
                type="vague_attribution",
                label=_LABELS["vague_attribution"],
                detail=f"Matched phrase: \"{m.group(0)}\"",
                source="heuristic",
                confidence=FLAG_CONFIDENCE["vague_attribution"],
                lang="en",
            ))
            break
    else:
        for pattern in _VAGUE_ATTR_PT:
            m = pattern.search(text)
            if m:
                flags.append(CredibilityFlag(
                    type="vague_attribution",
                    label=_LABELS["vague_attribution"],
                    detail=f"Matched phrase: \"{m.group(0)}\"",
                    source="heuristic",
                    confidence=FLAG_CONFIDENCE["vague_attribution"],
                    lang="pt",
                ))
                break

    # weasel_words (low confidence)
    for pattern in _WEASEL_EN:
        m = pattern.search(text)
        if m:
            flags.append(CredibilityFlag(
                type="weasel_words",
                label=_LABELS["weasel_words"],
                detail=f"Matched phrase: \"{m.group(0)}\"",
                source="heuristic",
                confidence=FLAG_CONFIDENCE["weasel_words"],
                lang="en",
            ))
            break
    else:
        for pattern in _WEASEL_PT:
            m = pattern.search(text)
            if m:
                flags.append(CredibilityFlag(
                    type="weasel_words",
                    label=_LABELS["weasel_words"],
                    detail=f"Matched phrase: \"{m.group(0)}\"",
                    source="heuristic",
                    confidence=FLAG_CONFIDENCE["weasel_words"],
                    lang="pt",
                ))
                break

    # emotional_manipulation (low confidence)
    for pattern in _EMOTIONAL_EN:
        m = pattern.search(text)
        if m:
            flags.append(CredibilityFlag(
                type="emotional_manipulation",
                label=_LABELS["emotional_manipulation"],
                detail=f"Matched word: \"{m.group(0)}\"",
                source="heuristic",
                confidence=FLAG_CONFIDENCE["emotional_manipulation"],
                lang="en",
            ))
            break

    # sensationalism (low confidence)
    for pattern in _SENSATIONALISM_EN:
        m = pattern.search(text)
        if m:
            flags.append(CredibilityFlag(
                type="sensationalism",
                label=_LABELS["sensationalism"],
                detail=f"Matched phrase: \"{m.group(0)}\"",
                source="heuristic",
                confidence=FLAG_CONFIDENCE["sensationalism"],
                lang="en",
            ))
            break

    return flags


# ---------------------------------------------------------------------------
# LLM scoring pass
# ---------------------------------------------------------------------------

SCORING_PROMPT = """\
You are a media literacy analyst. Assess the following news article for manipulative
or misleading journalistic patterns.

IMPORTANT CONSTRAINTS:
- Assess ONLY what is explicitly present in the provided headline and summary text.
- Do NOT infer content from the full article. Do NOT assume information exists that
  you cannot see in the provided text.
- When evidence is ambiguous or absent, return "uncertain", not "present".
- For every "present" verdict, you MUST quote the exact phrase or clause from the
  provided text that triggered the flag in the "detail" field.

Headline: {title}
Summary: {summary}

For each pattern type, return one of:
  - "present": the pattern is clearly present in the provided text
  - "absent": the pattern is not present
  - "uncertain": insufficient evidence in the provided text to determine

Pattern types and what to look for:
- betteridge: Headline ends in '?' implying a sensational claim the journalist won't assert as fact. NOT flagged if the question has a specific factual answer (dates, numbers, names).
- clickbait: Curiosity-gap language, emotional hooks, withholding information to force a click.
- vague_attribution: Claims attributed to unnamed sources IN THE PROVIDED TEXT. If a name or institution is present anywhere in text, this is absent.
- headline_mismatch: Headline's claim strength exceeds what the summary supports. Look for facts in the headline treated as speculation or accusation in the summary.
- weasel_words: Hedging that implies a strong claim while providing accountability cover ("could", "linked to", "raises concerns"). Only flag when the hedge is clearly being used to imply, not when it is appropriate epistemic caution.
- emotional_manipulation: Charged vocabulary disproportionate to the event described.
- passive_agency: Passive voice hiding a known, relevant actor.
- false_balance: False equivalence between positions with clearly unequal evidence.
- missing_context: Omitted information (base rates, timelines, conflicts of interest) that would materially change interpretation.
- sensationalism: Disproportionate scale framing — superlatives applied to ordinary events.

Review heuristic pre-flags and mark any as "cleared" that you assess are false positives:
{heuristic_flags}

Return JSON only:
{{
  "verdicts": {{
    "<pattern_type>": {{
      "verdict": "present" | "absent" | "uncertain",
      "detail": "<exact quote from provided text — REQUIRED when verdict is present>"
    }}
  }},
  "cleared_heuristic_flags": ["<flag_type>", ...]
}}"""


def _prompt_version() -> str:
    return hashlib.sha256(SCORING_PROMPT.encode()).hexdigest()[:12]


async def run_llm_scoring(
    title: str,
    summary: str,
    heuristic_flags: list[CredibilityFlag],
    client: "OpenRouterClient",
    model: str,
) -> list[CredibilityFlag]:
    """LLM scoring pass. Returns merged flag list. Never raises."""
    heuristic_summary = (
        json.dumps([{"type": f.type, "detail": f.detail} for f in heuristic_flags])
        if heuristic_flags
        else "none"
    )
    prompt = SCORING_PROMPT.format(
        title=title,
        summary=summary or "(no summary provided)",
        heuristic_flags=heuristic_summary,
    )

    try:
        response = await client.complete(
            messages=[{"role": "user", "content": prompt}],
            model=model,
            response_format={"type": "json_object"},
        )
        raw = response.content if hasattr(response, "content") else str(response)
        data = json.loads(raw)
    except Exception as exc:
        log.warning("credibility_llm_failed", error=str(exc))
        return heuristic_flags

    cleared: set[str] = set(data.get("cleared_heuristic_flags", []))
    surviving_heuristic = [f for f in heuristic_flags if f.type not in cleared]

    llm_flags: list[CredibilityFlag] = []
    verdicts = data.get("verdicts", {})
    for flag_type, verdict_obj in verdicts.items():
        if not isinstance(verdict_obj, dict):
            continue
        verdict = verdict_obj.get("verdict")
        detail = verdict_obj.get("detail", "")
        if verdict != "present" or not detail:
            continue
        if flag_type not in FLAG_CONFIDENCE:
            continue
        # Skip if already covered by a surviving heuristic flag of the same type
        already_present = any(f.type == flag_type for f in surviving_heuristic)
        if already_present:
            continue
        llm_flags.append(CredibilityFlag(
            type=flag_type,
            label=_LABELS.get(flag_type, flag_type),
            detail=detail,
            source="llm",
            confidence=FLAG_CONFIDENCE[flag_type],
        ))

    return surviving_heuristic + llm_flags


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def score_article(
    article: "Article",
    client: "OpenRouterClient",
    model: str,
    llm_enabled: bool = True,
) -> CredibilityReport:
    """Full two-pass scoring pipeline. Safe to call concurrently."""
    heuristic_flags = run_heuristics(article.title, article.summary)

    if not llm_enabled:
        return CredibilityReport(
            flags=heuristic_flags,
            status="heuristic_only",
            analyzed_at=datetime.now(timezone.utc),
        )

    llm_flags = await run_llm_scoring(
        article.title, article.summary, heuristic_flags, client, model
    )
    return CredibilityReport(
        flags=llm_flags,
        status="complete",
        analyzed_at=datetime.now(timezone.utc),
        model=model,
        prompt_version=_prompt_version(),
    )
