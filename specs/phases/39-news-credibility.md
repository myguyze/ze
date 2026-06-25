# News Credibility Analysis — Spec

> **Package:** `ze-news`
> **Phase:** 39
> **Status:** Done
> **Depends on:** Phase 37 ([37-news-package.md](37-news-package.md)), Phase 38 ([38-news-personalization.md](38-news-personalization.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `CredibilityFlag` / `CredibilityReport` types | ✅ Done |
| `credibility_analysis` DB column + migration | ✅ Done |
| Heuristic pre-pass (`ze_news/credibility.py`) | ✅ Done |
| LLM scoring pass | ✅ Done |
| Async scoring wired into fetch job | ✅ Done |
| `Article.credibility` exposed in `get_headlines` | ✅ Done |
| Briefing flag rendering with severity threshold | ✅ Done |
| Config block | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

News articles fetched from RSS sources vary widely in quality. Many use techniques
drawn from tabloid and engagement-optimised journalism — question headlines, phantom
sources, emotional manipulation, framing — that are designed to attract clicks rather
than inform accurately. These patterns are not always obvious, and they are distinct
from factual inaccuracy: an article can be technically true and still be structured to
mislead.

Ze already surfaces headlines to the user in the morning briefing and via the news
agent. Without credibility signals, Ze presents every article as equally trustworthy.
This phase adds a per-article credibility analysis step that detects known manipulative
patterns, stores a structured flag set alongside each article, and surfaces those flags
wherever headlines are shown — so the user can make an informed decision about what to
read rather than having the system make that decision for them.

Flagged articles are never filtered out. The system informs; it does not censor.

See [pre-mortem](39-news-credibility-premortem.md) for the full risk analysis.

---

## Pattern Taxonomy

These are the patterns the system detects. Each maps to a `flag_type` value in the
stored report. Every flag belongs to one of two confidence tiers that determine where
it is rendered (see Surfacing Flags). The distinction between heuristic-detectable and
LLM-required is important for the implementation architecture.

### High-Confidence Flags

These have clear linguistic signatures that can be verified against the text. They
carry low false-positive risk and are shown inline in the morning briefing.

---

#### `betteridge` — Question headline implying a claim the journalist won't commit to

**What it is.** Ian Betteridge's 2009 observation: any headline ending in a question
mark can be answered "no." The question format lets a publication insinuate something
sensational — a scandal, a risk, a connection — while the question mark provides
editorial and legal cover. If the journalist were confident in the claim, it would be
stated as fact.

**Examples.**
- "Is this the most corrupt government in history?"
- "Could your morning coffee be killing you?"
- "Did the CEO know about the fraud?"
- "Are we heading for another financial crash?"

**Detection.** Heuristic: headline ends with `?`. Language-agnostic — fires for all
sources. The LLM pass clears false positives where the question has a specific factual
answer ("What is the new VAT rate?", "When does the law take effect?").

---

#### `clickbait` — Curiosity-gap and engagement-bait language

**What it is.** Linguistic techniques that withhold information to force a click, or
exaggerate to provoke emotional engagement. The defining feature is that the headline
describes the reader's reaction to the story, not the story itself.

**Common patterns.**
- *Curiosity gap:* "You won't believe what happened next", "What this politician said
  will shock you", "The one thing X doesn't want you to know"
- *Withholding the subject:* "This is why [vague pronoun] is changing everything"
- *Numbered-list bait:* "7 reasons why X is worse than you think"
- *"...and it's worse than you think":* pure emotional ratcheting

**Detection.** Phrase matching against a curated list (heuristic). LLM for softer
variants ("Find out why...", "Discover the truth about...").

Portuguese variants included: "não vai acreditar", "vai chocar", "a verdade sobre".

---

#### `vague_attribution` — Phantom sources and anonymous authority

**What it is.** Claims attributed to unnamed, unverifiable, or implausibly vague
sources. Allows a journalist to assert something without standing behind it.

**Common forms.**
- *Phantom sources:* "Sources close to the situation say...", "Insiders claim..."
- *Anonymous experts:* "Some experts believe...", "Economists say..."
- *Unnamed reports:* "According to reports...", "Studies show..."
- *Passive attribution:* "It is claimed that...", "It has emerged that..."

**Why it matters.** Phantom sources are structurally unfalsifiable. The reader cannot
go and verify the claim because the source has no identity.

**Detection.** Phrase matching (heuristic) plus LLM for paraphrases.

**Important:** The LLM assesses only what is present in the provided headline and
summary. If the summary says "according to the report" and the full article names the
report in a hyperlink, the scorer cannot see that. The LLM is instructed to flag only
when the source is plainly unnamed in the provided text, and to prefer "uncertain"
when the phrasing is ambiguous.

Portuguese variants: "fontes dizem", "segundo fontes", "alegam fontes próximas".

---

#### `headline_mismatch` — Headline makes a stronger claim than the content supports

**What it is.** The headline states something as fact or near-fact that the summary
treats as speculation, preliminary, or contested. This exploits the reality that most
people read only the headline.

**Examples.**
- Headline: "Study proves coffee prevents Alzheimer's" / Summary: "A small
  observational study found a correlation; researchers caution causation is unproven."
- Headline: "Government to ban X" / Summary: "A minister said the government was
  'considering options' regarding X."

**Detection.** LLM required for full assessment — requires comparing claim strength
between headline and summary. Phase 81 adds an NLI heuristic pre-pass via `NLIClient`:
premise = summary, hypothesis = headline; flag when contradiction ≥ 0.50 or entailment
< 0.30 (cheaper than LLM for obvious mismatches). High confidence because the
comparison is anchored in the provided text.

---

### Low-Confidence Flags

These require contextual judgment, external knowledge, or interpretation of proportion.
They carry meaningful false-positive risk, particularly for local or niche topics.

Low-confidence flags are **never shown inline in the morning briefing** and do not
count toward the briefing summary total. They appear in `get_headlines` output and
agent responses with a `confidence: "low"` field and an explicit caveat.

---

#### `weasel_words` — Speculative hedging used to imply without accountability

**What it is.** Words and phrases that allow a strong implied claim while maintaining
plausible deniability. The claim is couched in uncertainty-language so the journalist
can say "we only said 'could'."

**Common weasel words.**
- *"Could", "might", "may":* "New drug could cure cancer"
- *"Reportedly", "allegedly":* repeating an unverified claim while appearing responsible
- *"Linked to":* correlation, causation, or statistical noise — "linked to" says nothing
- *"Raises concerns":* who? why? are they warranted?
- *"Questions remain":* used to keep a story alive after the main claim is undermined

**Why low-confidence.** "Could" in a scientific discovery story is appropriate
epistemic hedging. Context determines whether hedging is evasion or accuracy. The LLM
can distinguish these, but not reliably across all domains.

Portuguese variants: "alegadamente", "pode causar", "ligado a", "levanta questões".

---

#### `emotional_manipulation` — Disproportionate emotional language

**What it is.** Charged vocabulary where neutral language would be more accurate —
fear-inducing or outrage-maximising terms applied to routine events.

**Common signals.**
- *Fear-mongering:* "catastrophic", "devastating", "terrifying" applied to policy
- *Outrage bait:* "outrageous", "disgusting", "shameful" in headlines about
  contentious but ordinary events
- *Urgency inflation:* "BREAKING", "URGENT" on stories known for hours

**Why low-confidence.** "Devastating earthquake" is appropriate. "Devastating poll
results" is emotional inflation. Context determines proportionality. Lexicon matching
alone (heuristic) has a high false-positive rate; the LLM pass calibrates, but
"proportionate" is inherently subjective.

---

#### `passive_agency` — Passive voice used to conceal who did what

**What it is.** Structuring a sentence to hide the actor. "Mistakes were made" instead
of "The minister made mistakes." Frequently used to protect powerful actors.

**Common forms.**
- "It has been decided that..." (decided by whom?)
- "Funds were misappropriated" (by whom?)
- "The report was suppressed" (by whom?)

**Why low-confidence.** Passive voice is grammatically valid and often not evasive.
"The bill was signed" is fine when context makes the actor clear. The LLM can reason
about this, but false positives are common in summaries where the actor is named
elsewhere in the full article.

---

#### `false_balance` — False equivalence between unequal positions

**What it is.** Presenting two sides of a debate as equally evidence-supported when
one position has overwhelming expert or empirical backing.

**Classic examples.**
- Climate coverage that gives equal weight to scientific consensus and industry-funded
  sceptics
- Vaccine safety coverage that treats the retracted MMR-autism claim as a counterpoint

**Why low-confidence.** Detecting false balance requires knowing the state of expert
consensus on the specific topic being discussed. GPT-4o-mini is reliable on
well-known consensus topics (climate, vaccines) but will produce unreliable results
on niche, local, or contested topics. A false-balance flag on a Leiria municipal
planning dispute would be arbitrary.

---

#### `sensationalism` — Disproportionate framing of ordinary events

**What it is.** Framing a routine event as exceptional, historic, or catastrophic.
Scale distortion rather than emotional vocabulary.

**Common signals.**
- Unqualified superlatives: "the biggest", "the worst ever", "the first time in history"
- "Unprecedented" — one of the most abused words in news
- Scale inflation: "massive", "enormous" applied to routine events

**Why low-confidence.** "Unprecedented flooding" is sometimes accurate. "Unprecedented
earnings miss" is usually sensationalism. Whether a superlative is earned depends on
domain knowledge. Lexicon matching produces many false positives.

---

## Architecture

### Two-pass scoring

Detection runs in two passes per article, in sequence.

**Pass 1 — Heuristic pre-pass** (no LLM, runs inline during fetch)

Detects patterns identifiable by pattern matching alone. Runs on every article before
upsert. Flags: `betteridge`, `clickbait`, `vague_attribution`, `emotional_manipulation`,
`weasel_words`, `sensationalism`.

Heuristic flags include a `lang` field (`"any"` for language-agnostic patterns such as
`betteridge`; `"en"` or `"pt"` for phrase-based patterns). This makes coverage gaps
auditable.

Output: partial `CredibilityReport` with `status = "heuristic_only"`.

**Pass 2 — LLM scoring pass** (one API call per article, fires async post-upsert)

A cheap model (GPT-4o-mini) receives headline and summary and returns a structured JSON
report. The LLM:
- Assesses all 10 pattern types with `"present" | "absent" | "uncertain"` verdicts
- Requires a verbatim quote from the provided text in `detail` for every `"present"` verdict
- Reviews heuristic flags and returns `"cleared"` for any assessed as false positives
- Defaults to `"uncertain"` when evidence in the provided text is ambiguous

Only `"present"` verdicts produce stored flags. `"uncertain"` is discarded. This
makes the system conservative — it will miss some real patterns but avoid false
accusations.

Output: `CredibilityReport` updated with LLM flags, `status = "complete"`,
`prompt_version` set to the first 12 characters of the SHA-256 of the scoring prompt.

Articles are scored once. Re-scoring is triggered explicitly via
`POST /news/rescore?version_mismatch_only=true` when the prompt changes.

---

## Data Structures

```python
# ze_news/types.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

FlagType = Literal[
    "betteridge",
    "clickbait",
    "vague_attribution",
    "headline_mismatch",       # high-confidence
    "weasel_words",
    "emotional_manipulation",
    "passive_agency",
    "false_balance",
    "missing_context",
    "sensationalism",          # low-confidence
]

FlagConfidence = Literal["high", "low"]

# Maps flag type to its confidence tier.
# High-confidence: shown inline in briefing, counted in summary.
# Low-confidence: available in get_headlines and agent responses only.
FLAG_CONFIDENCE: dict[FlagType, FlagConfidence] = {
    "betteridge":           "high",
    "clickbait":            "high",
    "vague_attribution":    "high",
    "headline_mismatch":    "high",
    "weasel_words":         "low",
    "emotional_manipulation": "low",
    "passive_agency":       "low",
    "false_balance":        "low",
    "missing_context":      "low",
    "sensationalism":       "low",
}

AnalysisStatus = Literal["pending", "heuristic_only", "complete", "failed"]


@dataclass
class CredibilityFlag:
    type: FlagType
    label: str              # descriptive label, e.g. "Sources unnamed" (not "Phantom sources")
    detail: str             # exact phrase or structure that triggered the flag
    source: Literal["heuristic", "llm"]
    confidence: FlagConfidence   # derived from FLAG_CONFIDENCE[type]
    lang: str = "any"       # "any" | "en" | "pt" — for heuristic flags only


@dataclass
class CredibilityReport:
    flags: list[CredibilityFlag] = field(default_factory=list)
    status: AnalysisStatus = "pending"
    analyzed_at: datetime | None = None
    model: str | None = None         # model used for LLM pass; null if heuristic-only
    prompt_version: str | None = None  # first 12 chars of SHA-256 of scoring prompt
```

`Article` gains an optional `credibility` field:

```python
@dataclass
class Article:
    url: str
    source_key: str
    title: str
    summary: str
    published_at: datetime
    tags: list[str] = field(default_factory=list)
    credibility: CredibilityReport | None = None   # None = not yet scored
```

Convenience helpers on `CredibilityReport`:

```python
@property
def high_confidence_flags(self) -> list[CredibilityFlag]:
    return [f for f in self.flags if f.confidence == "high"]

@property
def is_briefing_worthy(self) -> bool:
    """True when the article has enough high-confidence signal to show inline."""
    hf = self.high_confidence_flags
    return len(hf) >= 2 or any(f.type in ("betteridge", "clickbait", "headline_mismatch") for f in hf)
```

---

## Storage

New nullable JSONB column on `news_articles`:

```sql
-- migration zn002_credibility_analysis.py

ALTER TABLE news_articles
  ADD COLUMN credibility_analysis JSONB DEFAULT NULL;
```

Stored as:
```json
{
  "flags": [
    {
      "type": "betteridge",
      "label": "Question headline",
      "detail": "Headline ends with '?' — implies a claim the author won't assert as fact.",
      "source": "heuristic",
      "confidence": "high",
      "lang": "any"
    },
    {
      "type": "vague_attribution",
      "label": "Sources unnamed",
      "detail": "'Sources close to the situation' is not attributed to any named party.",
      "source": "llm",
      "confidence": "high",
      "lang": "any"
    }
  ],
  "status": "complete",
  "analyzed_at": "2026-06-07T08:30:00Z",
  "model": "openai/gpt-4o-mini",
  "prompt_version": "a3f9c2d14e7b"
}
```

No new table. JSONB is sufficient — the only query pattern is "article with its
report." A separate table would add a join on every `get_headlines` call with no
benefit.

---

## Module Location

```
packages/ze-news/
  ze_news/
    types.py             ← add CredibilityFlag, CredibilityReport, FLAG_CONFIDENCE
    credibility.py       ← new: run_heuristics(), run_llm_scoring(), score_article()
    store.py             ← update _row_to_article(), add update_credibility()
    jobs/
      fetch.py           ← wire scoring into post-upsert step
    migrations/
      versions/
        zn002_credibility_analysis.py   ← new migration
```

No changes to `ze/` or `ze_core/`. Credibility is a `ze-news`-internal concern.

---

## `ze_news/credibility.py`

```python
# Heuristic analyser — no I/O, pure functions

BETTERIDGE_RE = re.compile(r'\?\s*$')

CLICKBAIT_PHRASES_EN = [
    r"you won't believe",
    r"will shock you",
    r"doesn't want you to know",
    r"the truth about",
    r"here's why",
    r"find out why",
    r"this is what happens",
    r"\d+ reasons? (?:why|to|that)",
    r"and it(?:'s| is) worse than you think",
    r"what happened next",
    r"changed everything",
]
CLICKBAIT_PHRASES_PT = [
    r"não vai acreditar",
    r"vai chocar",
    r"a verdade sobre",
    r"descubra porquê",
    r"isto vai mudar tudo",
]

WEASEL_PHRASES_EN = [
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
WEASEL_PHRASES_PT = [
    r"\balegadamente\b",
    r"\bpode causar\b",
    r"\bligado a\b",
    r"\blevanta questões\b",
    r"\bfontes dizem\b",
    r"\bsegundo fontes\b",
]

EMOTIONAL_WORDS_EN = [
    "catastrophic", "devastating", "terrifying", "horrifying",
    "outrageous", "disgusting", "shameful", "unforgivable",
]
SENSATIONALISM_WORDS_EN = [
    "unprecedented", "historic", "first time in history",
    "worst ever", "biggest ever",
]


def run_heuristics(title: str, summary: str) -> list[CredibilityFlag]:
    """
    Fast, zero-cost pre-pass. High-precision, not high-recall.
    Prefers false negatives over false positives.
    """
    ...


# LLM analyser

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
}}
"""


async def run_llm_scoring(
    title: str,
    summary: str,
    heuristic_flags: list[CredibilityFlag],
    client: OpenRouterClient,
    model: str,
) -> list[CredibilityFlag]:
    """
    LLM scoring pass. Returns merged flag list (heuristic flags minus cleared ones,
    plus new LLM "present" verdicts). Returns heuristic_flags unchanged on any error.
    Never raises.
    """
    ...


async def score_article(
    article: Article,
    client: OpenRouterClient,
    model: str,
    llm_enabled: bool = True,
) -> CredibilityReport:
    """
    Full two-pass scoring pipeline. Returns a complete CredibilityReport.
    Safe to call concurrently for multiple articles.
    """
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


def _prompt_version() -> str:
    import hashlib
    return hashlib.sha256(SCORING_PROMPT.encode()).hexdigest()[:12]
```

---

## Fetch Job Integration

After the upsert loop in `NewsFetchJob`, scoring fires for newly inserted articles as
a fire-and-forget task:

```python
async def run(self) -> None:
    for source in self._registry.all():
        articles = await source.fetch()
        new_count = await self._store.upsert(articles)
        if new_count > 0:
            asyncio.create_task(
                self._score_new_articles(articles[-new_count:])
            )

async def _score_new_articles(self, articles: list[Article]) -> None:
    for article in articles:
        try:
            report = await score_article(
                article,
                client=self._client,
                model=self._credibility_model,
                llm_enabled=self._llm_scoring_enabled,
            )
            await self._store.update_credibility(article.url, report)
        except Exception:
            log.warning("credibility_scoring_failed", url=article.url)
```

**Graceful degradation:** if an article reaches the morning briefing before scoring
completes (`credibility = None`), it is rendered without flags. No placeholder or
warning is shown — the briefing is degraded silently, which is correct: the user
receives accurate headlines without flag noise during the scoring window.

---

## `NewsStore` Changes

```python
async def update_credibility(self, url: str, report: CredibilityReport) -> None:
    """Write a CredibilityReport to news_articles.credibility_analysis."""
    ...

# _row_to_article updated to deserialise credibility_analysis JSON into CredibilityReport
# when the column is non-null. Returns Article with credibility=None when column is NULL.
```

---

## Surfacing Flags

### Rendering rules by tier

**High-confidence flags** (`betteridge`, `clickbait`, `vague_attribution`,
`headline_mismatch`):
- Shown inline in the morning briefing when `is_briefing_worthy` is True
- Counted in the briefing summary line
- Shown in `get_headlines` output with full `confidence` field
- The agent presents them directly: "Ze noted: sources unnamed"

**Low-confidence flags** (`weasel_words`, `emotional_manipulation`, `passive_agency`,
`false_balance`, `missing_context`, `sensationalism`):
- Never shown inline in morning briefing
- Not counted in briefing summary line
- Shown in `get_headlines` output with `confidence: "low"`
- The agent presents them with a caveat: "Ze noticed this may be worth noting, though
  it can only assess what's in the summary..."

### Icon and label language

Use 🔍 (not ⚠️). The observation icon signals "Ze noticed something" without
positioning Ze as a media critic. Labels are **descriptive**, not evaluative:

| Flag type | Label (not) | Label (use) |
|---|---|---|
| betteridge | "Misleading question" | "Question headline" |
| clickbait | "Bait headline" | "Engagement hook language" |
| vague_attribution | "Phantom sources" | "Sources unnamed" |
| headline_mismatch | "Misleading headline" | "Headline stronger than summary" |
| weasel_words | "Weasel words" | "Hedged claim language" |
| emotional_manipulation | "Emotional bait" | "Heightened emotional language" |
| passive_agency | "Hidden actor" | "Actor not named" |
| false_balance | "False balance" | "Unequal positions presented equally" |
| missing_context | "Missing context" | "Context may be incomplete" |
| sensationalism | "Sensationalism" | "Disproportionate framing" |

### `get_headlines` tool

Each article dict gains a `credibility` key:

```json
{
  "title": "Is this the worst government ever?",
  "url": "...",
  "source": "bbc_world",
  "published_at": "...",
  "credibility": {
    "flags": [
      {
        "type": "betteridge",
        "label": "Question headline",
        "detail": "Headline ends with '?' — implies a claim the author won't assert as fact.",
        "confidence": "high"
      }
    ],
    "status": "complete"
  }
}
```

`credibility` is `null` when the article has not yet been scored.

### Morning briefing

**Relevant bucket (`📰 For you`):** inline labels shown when `is_briefing_worthy` is
True. Label format is `🔍 <label>` appended after the source key.

```
📰 For you (based on your interests):
  • Is this the worst PM ever? (bbc_world) 🔍 question headline
  • AI chip breakthrough doubles performance (bbc_tech)
  • Sources say economy may collapse (dn) 🔍 sources unnamed, headline stronger than summary
```

**Discovery bucket (`🔭 Outside your usual`):** no inline labels. Discovery articles
are already contextualised as off-profile; adding credibility labels creates a
double-negative presentation. Flags for discovery articles are visible in full in
agent responses.

**Summary line:** shown at the end of the news section when ≥1 high-confidence flag
exists AND flagged articles are <50% of the relevant bucket. When everything is
flagged, the summary line is omitted — at that density, the count conveys no signal.

```
  (2 of 6 articles flagged for potentially misleading patterns)
```

---

## Configuration

```yaml
# config/config.yaml

news:
  credibility:
    enabled: true
    llm_scoring: true              # false → heuristic-only (zero LLM cost, lower recall)
    model: "openai/gpt-4o-mini"    # model for LLM scoring pass
    flag_in_briefing: true         # show inline flags in morning briefing
    briefing_summary: true         # show "N of M articles flagged" summary line
    briefing_flag_threshold: 2     # min high-confidence flags for inline briefing display
                                   # (1 allows single betteridge/clickbait/headline_mismatch)
```

`llm_scoring: false` gives a useful intermediate state — heuristics are free and catch
the most obvious patterns. Operators who want zero incremental cost can run
heuristics-only and still surface Betteridge violations, clickbait phrases, and
common weasel words.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.openrouter.client.OpenRouterClient` | LLM scoring pass |
| `ze_core.logging.get_logger` | Structured logging |
| `ze_news.store.NewsStore` | `update_credibility()` |
| `ze_news.types.CredibilityReport` | Return type of scorer |

`NewsFetchJob` already receives `OpenRouterClient` — no new constructor args needed.
The credibility model is configurable separately from the news agent model.

---

## Implementation Notes

- **Why JSONB, not a separate table?** There is one credibility report per article.
  The only query pattern is "article with its report." A separate table adds a join
  on every `get_headlines` call with no benefit.

- **Why async scoring?** At 20 new articles per fetch with ~300ms per LLM call,
  synchronous scoring adds 6 seconds to the fetch loop. Fire-and-forget keeps the
  loop fast. Graceful degradation (render without flags) handles the rare case where
  scoring hasn't completed before the briefing runs.

- **Why not re-score periodically?** An article's credibility properties are fixed at
  publication. Re-scoring wastes API calls. When the scoring prompt changes, use
  `POST /news/rescore?version_mismatch_only=true` — this targets only articles whose
  stored `prompt_version` differs from the current one, making re-scoring precise.

- **Flag fatigue mitigation.** The `is_briefing_worthy` property and the 50% threshold
  on the summary line are the key guards. Single low-signal flags (one `weasel_words`
  hit) produce no visible output in the briefing. The user sees flags only when
  multiple signals converge or when a high-severity single pattern is unambiguous.

- **False positive tolerance.** The heuristic pre-pass is high-precision, not
  high-recall. The LLM prompt requires verbatim quotes from the provided text in every
  `detail` field. This makes every flag self-auditable and forces the LLM to anchor
  its verdicts in evidence rather than inference.

- **Prompt stability and versioning.** `prompt_version` is stored on every report.
  Changes to `SCORING_PROMPT` change the hash and allow targeted re-scoring. Treat
  prompt changes as schema changes — they alter the semantics of stored flag types.

- **`false_balance` and `missing_context` are low-confidence by design.** These flags
  require external knowledge (expert consensus state, base rate data) that cannot be
  reliably inferred from headline + summary alone. They are retained because when they
  fire correctly they are valuable (a clearly false-balance climate headline is worth
  noting). Restricting them to low-confidence and excluding them from the briefing
  contains the false-positive surface area.

- **Multilingual heuristics.** Portuguese phrase lists are included for `clickbait`,
  `weasel_words`, and `vague_attribution`. `betteridge` is language-agnostic. The LLM
  pass handles all languages without changes. Heuristic flags include a `lang` field
  (`"en"`, `"pt"`, `"any"`) so coverage gaps are auditable. Full heuristic parity
  across all source languages is a v2 concern.

- **No flag suppression per source.** Silently suppressing flags from "trusted" sources
  would undermine the transparency goal. The user sees flags; they decide. A
  descriptive label ("Sources unnamed") on a Reuters article is an observation, not a
  judgment about Reuters. The user is equipped to disagree.

- **User preference via memory.** If the user says "Ze, I don't care about question
  headlines" in conversation, memory stores a UserFact. A future extension can read
  this fact in `_build_personalization_ctx()` and exclude specific flag types from
  display. This requires no new machinery — it follows the existing preference signal
  pattern from Phase 38. Out of scope for v1; the memory path is the natural
  implementation when needed.
