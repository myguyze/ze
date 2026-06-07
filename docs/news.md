# Ze — News Package (`ze-news`)

The `ze-news` plugin adds RSS ingestion, personalised article ranking, and credibility
analysis to Ze. It runs as a `ZePlugin`, keeping all news-specific concerns isolated
from `ze-core` and `ze-personal`.

---

## Architecture overview

```
config.yaml (news.sources)
        │
        ▼
SourceRegistry ──► RssSource.fetch() ──► NewsFetchJob
                                               │
                        ┌──────────────────────┤
                        │                      │
                        ▼                      ▼
                 NewsStore.upsert()    async credibility scoring
                        │                      │
                 (embedding stored)    NewsStore.update_credibility()
                        │
           ┌────────────┼────────────┐
           │            │            │
           ▼            ▼            ▼
    get_headlines   search_news   MorningBriefing
    (news agent)   (news agent)   (briefing job)
```

---

## Package layout

```
packages/ze-news/
  ze_news/
    types.py          ← Article, CredibilityFlag, CredibilityReport, PersonalizationContext
    store.py          ← NewsStore: upsert, get_recent, get_personalized, search, update_credibility
    registry.py       ← SourceRegistry, build_registry()
    credibility.py    ← run_heuristics(), run_llm_scoring(), score_article()
    plugin.py         ← NewsPlugin(ZePlugin): agents, jobs, migrations, configurable_services
    sources/
      base.py         ← NewsSource ABC
      rss.py          ← RssSource (feedparser + aiohttp)
    agents/
      agent.py        ← NewsAgent(@agent)
      tools.py        ← get_headlines, search_news tools
    jobs/
      fetch.py        ← NewsFetchJob(@proactive_job)
    migrations/
      versions/
        zn001_news_articles.py        ← creates news_articles table
        zn002_credibility_analysis.py ← adds credibility_analysis JSONB column
```

---

## Data model

### `Article`

```python
@dataclass
class Article:
    url: str
    source_key: str          # matches the key in config.yaml sources list
    title: str
    summary: str
    published_at: datetime
    tags: list[str]          # copied from source config at fetch time
    credibility: CredibilityReport | None  # None = not yet scored
```

### `news_articles` table

| Column | Type | Notes |
|---|---|---|
| `url` | `TEXT PK` | Deduplication key |
| `source_key` | `TEXT` | Source identifier |
| `title` | `TEXT` | Article headline |
| `summary` | `TEXT` | RSS summary / lede |
| `published_at` | `TIMESTAMPTZ` | Publication timestamp from RSS |
| `tags` | `TEXT[]` | Tags from source config |
| `embedding` | `VECTOR(384)` | `paraphrase-multilingual-MiniLM-L12-v2` on `title + summary` |
| `credibility_analysis` | `JSONB` | `CredibilityReport` serialised; `NULL` until scored |
| `fetched_at` | `TIMESTAMPTZ` | When Ze first ingested the article |

---

## Fetch job

`NewsFetchJob` runs on a cron (default: every 30 minutes). For each source it:

1. Calls `source.fetch(limit=50)` — fetches and parses the RSS feed.
2. Embeds each article (`title + summary`) using the shared
   `paraphrase-multilingual-MiniLM-L12-v2` singleton.
3. Upserts into `news_articles` (`ON CONFLICT (url) DO NOTHING`).
4. Returns the list of newly inserted articles.
5. If `news.credibility.enabled: true` and new articles exist, fires an
   `asyncio.create_task` to score them — scoring never blocks the fetch loop.
6. Prunes articles older than `news.retention_days`.

---

## Personalisation

### How it works

When the news agent or morning briefing requests personalised headlines, Ze builds
a `PersonalizationContext` from memory:

```python
@dataclass
class PersonalizationContext:
    interest_text: str       # pipe-joined "key: value" facts + active goal titles
    exclusions: list[str]    # values from facts with exclusion keys ("not interested", "avoid", ...)
    explore_ratio: float     # fraction of results reserved for discovery (default: 0.2)
    fact_count: int          # number of non-exclusion facts (used to check min_facts threshold)
```

`NewsStore.get_personalized()` then:

1. If `fact_count < min_facts` or `interest_text` is empty — falls back to plain
   recency ordering and returns `(articles, [])`. The caller treats this as
   "not enough signal yet."
2. Otherwise, fetches `limit × candidate_multiplier` recent articles as candidates.
3. Applies word-boundary exclusions (regex `\bterm\b`) — articles whose title or
   summary match any exclusion term are dropped.
4. Scores the remaining candidates by cosine similarity against the interest vector
   (numpy dot-product over L2-normalised embeddings).
5. Splits into two buckets:
   - **Relevant** — top `ceil((1 − explore_ratio) × limit)` articles by score.
   - **Discovery** — remaining candidates, re-sorted by recency (`published_at DESC`),
     up to `limit − len(relevant)`.

### Preference signals

No new UI is needed. When the user says *"Ze, I don't care about football"*, memory
stores a `UserFact(key="not interested in", value="football")`. On the next context
build, "football" appears in `exclusions` and is filtered from both buckets using
word-boundary regex — so "sport" won't falsely exclude "transport" articles.

### Briefing rendering

```
📰 For you (based on your interests):
  • Article title (source_key)  🔍 question headline
  • Another article (source_key)

  (1 of 5 articles flagged for potentially misleading patterns)

🔭 Outside your usual:
  • Off-profile article (source_key)
```

- The "For you" header appears when `fact_count ≥ min_facts`. Below the threshold it
  falls back to `📰 Headlines:`.
- Discovery articles never show inline credibility labels (to avoid double-negative
  framing). Their flags are available via the news agent.
- The summary line is shown only when flagged articles are fewer than 50% of the
  relevant bucket — at higher density the count conveys no useful signal.

---

## Credibility analysis

Ze flags articles for manipulative or misleading journalistic patterns. Flagged
articles are never filtered out — the system informs, it does not censor.

### Two-pass architecture

**Pass 1 — Heuristic pre-pass** (inline, zero cost)

Runs on every new article immediately after upsert. Pure phrase and regex matching
against the title and summary. Produces `CredibilityFlag` objects with
`source="heuristic"`.

**Pass 2 — LLM scoring pass** (async, one API call per article)

Fires as a background task via `asyncio.create_task` after upsert. A cheap model
(GPT-4o-mini by default) receives the headline and summary and returns a structured
JSON report with verdicts for all 10 pattern types. The LLM:

- Requires a verbatim quote from the provided text in `detail` for every `"present"`
  verdict — making every flag self-auditable.
- Defaults to `"uncertain"` when evidence is ambiguous — the system prefers false
  negatives over false positives.
- Reviews heuristic flags and can `"clear"` them if assessed as false positives on the
  full article context.

Articles that reach the 8 AM briefing before scoring completes are rendered without
flags (graceful degradation). No placeholder is shown.

### Flag taxonomy

Flags belong to one of two confidence tiers, which control where they are rendered.

**High-confidence** (clear linguistic signatures, low false-positive risk):

| Flag | Label shown | Detection |
|---|---|---|
| `betteridge` | Question headline | Headline ends in `?` (language-agnostic) |
| `clickbait` | Engagement hook language | EN + PT phrase lists, then LLM |
| `vague_attribution` | Sources unnamed | EN + PT phrase lists, then LLM |
| `headline_mismatch` | Headline stronger than summary | LLM only |

**Low-confidence** (require contextual judgment, higher false-positive risk):

| Flag | Label shown | Why low-confidence |
|---|---|---|
| `weasel_words` | Hedged claim language | "Could" is sometimes appropriate epistemic caution |
| `emotional_manipulation` | Heightened emotional language | "Devastating earthquake" is accurate, not manipulation |
| `passive_agency` | Actor not named | Passive voice is grammatically valid; actor may be named elsewhere |
| `false_balance` | Unequal positions presented equally | Requires knowing expert consensus state; unreliable for niche topics |
| `missing_context` | Context may be incomplete | Requires external knowledge of what context is relevant |
| `sensationalism` | Disproportionate framing | "Unprecedented flooding" may be accurate |

### Rendering rules

| Tier | Briefing inline | Briefing count | `get_headlines` | Agent response |
|---|---|---|---|---|
| High-confidence | ✅ when `is_briefing_worthy` | ✅ | ✅ with `confidence` field | Direct: "Ze noted: sources unnamed" |
| Low-confidence | ❌ | ❌ | ✅ with `confidence: "low"` | Caveated: "Ze noticed this may be worth noting…" |

`is_briefing_worthy` is true when an article has ≥ 2 high-confidence flags **or** a
single flag of type `betteridge`, `clickbait`, or `headline_mismatch`. A lone
`vague_attribution` flag does not show inline — it requires corroborating signal.

The 🔍 icon is used throughout (not ⚠️). It signals observation, not condemnation.
Labels are descriptive, not evaluative: "Sources unnamed" rather than "Phantom sources."

### Prompt versioning

The LLM scoring prompt's SHA-256 (first 12 characters) is stored on every
`CredibilityReport` as `prompt_version`. When the prompt changes, only articles whose
stored version differs from the current one need re-scoring — targeted via:

```bash
POST /news/rescore?version_mismatch_only=true
```

Treat prompt changes as schema changes: they alter the semantics of stored flag types.

---

## Configuration

```yaml
news:
  enabled: true
  fetch_schedule: "*/30 * * * *"   # cron for fetch job
  retention_days: 7                 # hard-delete articles older than N days
  model: "openai/gpt-4o-mini"      # news agent model
  briefing_limit: 8                 # fallback if personalization.briefing_limit not set

  personalization:
    enabled: true
    explore_ratio: 0.2             # fraction of briefing reserved for discovery
    candidate_multiplier: 3        # over-fetch multiplier before scoring
    briefing_limit: 8              # total articles in morning briefing (≥ 8 recommended)
    min_facts: 5                   # min user facts before scoring; below → recency fallback

  credibility:
    enabled: true
    llm_scoring: true              # false → heuristic-only (zero LLM cost)
    model: "openai/gpt-4o-mini"   # model for LLM scoring pass
    flag_in_briefing: true         # show 🔍 labels inline in morning briefing
    briefing_summary: true         # show "N of M articles flagged" summary line

  sources:
    - key: bbc_world
      type: rss
      url: "https://feeds.bbci.co.uk/news/world/rss.xml"
      tags: [global, general]
```

**`explore_ratio`** — `0.0` = fully interest-ranked (filter bubble). `1.0` = all
discovery. Default `0.2` means one in five briefing headlines is deliberately off-profile.

**`briefing_limit`** must be ≥ 8 for the 80/20 split to produce at least 2 discovery
articles. At `limit=5`, `ceil(0.2 × 5) = 1` — a single discovery article is not
meaningful serendipity.

**`credibility.llm_scoring: false`** gives a useful intermediate state: heuristics
are free and catch Betteridge violations, clickbait phrases, and common weasel words.
Useful if OpenRouter costs become a concern (`~$1/day` at current source volume).

**Source tags** are arbitrary strings. Useful conventions: `global`, `local`, `tech`,
`pt`, `leiria`, `hacker-news`. Both `get_headlines` and the briefing accept a `tags`
filter.

---

## Adding a source

Add an entry under `news.sources` in `config/config.yaml`:

```yaml
- key: my_source         # unique identifier used as source_key on articles
  type: rss
  url: "https://example.com/feed.xml"
  tags: [global, tech]   # arbitrary; used for filtering
```

Sources are registered at startup. A full restart is required when adding or removing
sources (`enabled` flag changes also require restart; hot-reload via SIGHUP does not
apply to the news plugin).

---

## `get_headlines` tool

The news agent exposes two tools:

**`get_headlines`** — returns ranked headlines. The LLM schema accepts `limit`,
`tags`, and `personalized`. When `personalized=true` (default), the tool injects
the current session's `PersonalizationContext` automatically and returns:

```json
{
  "relevant": [
    {
      "title": "Is this the worst PM ever?",
      "url": "https://...",
      "source": "bbc_world",
      "published_at": "2026-06-07T08:00:00+00:00",
      "tags": ["global", "general"],
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
  ],
  "discovery": [...]
}
```

`credibility` is `null` when the article has not yet been scored.

**`search_news`** — semantic search via pgvector cosine similarity. Accepts `query`,
`limit`, and optional `tags` filter.

---

## Multilingual support

The embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) handles all source
languages without changes. Portuguese sources (DN, Observador, Jornal de Leiria) are
embedded and ranked correctly alongside English sources.

Heuristic credibility detection has partial Portuguese coverage:

| Pattern | EN | PT |
|---|---|---|
| `betteridge` | ✅ (language-agnostic — `?` suffix) | ✅ |
| `clickbait` | ✅ | ✅ (common PT formulas) |
| `vague_attribution` | ✅ | ✅ |
| `weasel_words` | ✅ | ✅ |
| `headline_mismatch` | ✅ (LLM) | ✅ (LLM handles PT) |
| Other low-confidence | ✅ (EN only) | ❌ (LLM handles PT) |

Full heuristic parity across all languages is a v2 concern. Heuristic flags carry a
`lang` field (`"en"`, `"pt"`, `"any"`) so coverage gaps are auditable.

---

## Inspecting news data

| Endpoint | Description |
|---|---|
| `GET /news/articles` | Recent articles with credibility data |
| `POST /news/rescore` | Trigger credibility re-scoring (`?version_mismatch_only=true`) |

Or via the news agent in conversation:
- *"What's in the news today?"* — `get_headlines` with default personalization
- *"Any tech news?"* — `get_headlines(tags=["tech"])`
- *"Search for articles about the budget"* — `search_news(query="budget")`
- *"Were any of today's headlines flagged?"* — agent surfaces credibility flags with context
