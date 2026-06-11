# News Preference Model — Spec

> **Package:** `ze-news`, `ze-memory`
> **Phase:** 50
> **Status:** Pending
> **Depends on:** Phase 38 ([38-news-personalization.md](38-news-personalization.md)), Phase 39 ([39-news-credibility.md](39-news-credibility.md)), Core Memory ([../core/06-memory.md](../core/06-memory.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| News preference signal model | 🔲 Pending |
| Context builder replacement | 🔲 Pending |
| News exclusions and saturation controls | 🔲 Pending |
| Memory/profile integration | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

The existing news personalization path builds `PersonalizationContext` from the most
recent memory facts and active goals. That is too broad. A fresh fact like "the user
likes bananas" can dominate headline selection even when the user did not ask for
fruit, and a follow-up like "why are you showing me bananas?" can accidentally
reinforce the topic.

This phase replaces "recent facts as interests" with an explicit news preference
model. News ranking should use facts only when they are suitable personalization
signals, should respect negative preferences, and should keep user-visible answers
grounded in the current request.

---

## Responsibilities

- Define which memory signals are allowed to influence news ranking.
- Separate durable news preferences from incidental or diagnostic facts.
- Apply explicit exclusions before ranking.
- Use the current news request as a first-class ranking signal.
- Prevent one topic from saturating the feed.
- Make personalization explainable enough that Ze can answer "why did you show this?"
  without inventing a supporting fact.
- Cover regressions with unit tests around topic over-personalization.

---

## Out of Scope

- Click/view tracking and implicit engagement telemetry.
- A thumbs-up/thumbs-down UI.
- Model training, collaborative filtering, or per-user embedding stores.
- Cross-user recommendations.
- Replacing the memory extractor globally. This phase only constrains how news consumes
  memory.
- Real-time web search. The news agent still uses the local curated news store.

---

## Problem Statement

News currently treats a recent memory snapshot as a bag of interests:

```python
facts = await memory_store.list_recent_facts(days=90, limit=30)
interest_text = " | ".join(f"{f.predicate}: {f.value}" for f in facts)
```

That creates three failure modes:

- **Recency is not preference.** "I asked why you keep showing bananas" is recent, but
  it is not a request for more bananas.
- **All facts are not news interests.** Activity facts like "programming an AI assistant"
  may be useful context in conversation, but should not automatically steer headlines.
- **No saturation control.** A single strong topic can crowd out the rest of the feed.

The target behavior is:

- If the user asks "what's in the news?", use durable news preferences plus controlled
  discovery.
- If the user asks "tech headlines", prioritize tech even if fruit is a known
  interest.
- If the user asks "why bananas?", answer from explicit preference/exclusion evidence
  and do not treat the question as positive interest.
- If the user says "stop showing bananas", suppress banana-related articles until the
  preference changes.

---

## Signal Taxonomy

News personalization may use only these signal classes:

| Signal | Source | Weight | Notes |
| ------ | ------ | ------ | ----- |
| `news_interest` | explicit user fact or profile facet | High | "Show me AI news", "I care about Portuguese politics" |
| `news_exclusion` | explicit negative user fact or profile facet | Blocking | "Don't show me bananas", "I don't care about fruit" |
| `topic_interest` | stable profile facet | Medium | General interests that are suitable for news, such as AI or economics |
| `active_goal` | goal titles | Medium | Current projects can influence tech/business news |
| `current_query` | user's current prompt | High | Always dominates broad preference matching |
| `discovery` | recency/source diversity | Low | Keeps filter-bubble resistance |

The news layer must not use these as positive personalization signals:

- transient activity facts, for example `activity_programming`
- assistant diagnostics, for example "user asked why Ze suggested bananas"
- contact facts
- facts about third parties
- unreviewed facts below the confidence threshold
- negative facts as positive interests

---

## Data Structures

No new database table is required for v1. The news layer consumes projected preferences
from memory facts/profile facets.

```python
# ze_news/types.py

@dataclass
class NewsPreference:
    topic: str
    polarity: Literal["include", "exclude"]
    source: Literal["fact", "profile", "goal", "query"]
    weight: float
    reason: str
    confidence: float = 1.0


@dataclass
class PersonalizationContext:
    query_text: str
    preferences: list[NewsPreference]
    explore_ratio: float = 0.2
    max_per_topic: int = 2
```

`reason` is short text Ze can use when explaining why an article was selected, e.g.
`"stored news preference: AI"` or `"matches your current request: tech headlines"`.

---

## Building Preferences

Create a small builder in `ze_news/preferences.py`:

```python
class NewsPreferenceBuilder:
    def __init__(self, memory_store: PostgresMemoryStore, goal_provider: GoalTitleProvider) -> None: ...

    async def build(self, query_text: str) -> PersonalizationContext: ...
```

### Fact Selection

The builder should prefer structured predicates over free-form recency:

- Include facts whose predicate starts with `news_interest`, `interest_news`, or
  `topic_interest`.
- Include stable profile facets whose key is `topics`, `preferences`, or
  `news_preferences`, but split them into individual topic strings before scoring.
- Include active goal titles as lower-weight preferences.
- Include the current query as a high-weight preference unless the query is a diagnostic
  or preference-management request.

### Exclusions

Build exclusions from both predicate and value text. The current implementation checks
only the predicate, which misses facts like:

```text
preference: don't show me bananas
```

Negative patterns include:

- `don't show`
- `do not show`
- `not interested`
- `don't care about`
- `avoid`
- `stop showing`
- `less <topic>`
- `no <topic>`

The extracted exclusion topic should be the topic, not the whole sentence, when it can
be parsed conservatively.

### Diagnostic Query Detection

Preference-management and diagnostic prompts must not become interests:

- "why do you keep showing bananas?"
- "show me the fact that says I like bananas"
- "stop suggesting bananas"
- "do you think I care about fruit?"

For these prompts:

- `query_text` remains available to the agent for answering.
- The builder may produce exclusions or inspection hints.
- The builder must not add a positive `query` preference for the mentioned topic.

---

## Ranking Algorithm

`NewsStore.get_personalized()` should rank candidates using three scores:

```text
score = query_score + preference_score + freshness_score - exclusion_penalty
```

- `query_score`: semantic similarity between article text and current user prompt.
- `preference_score`: weighted max or weighted average similarity to include preferences.
- `freshness_score`: small normalized recency boost.
- `exclusion_penalty`: blocking filter for exact/word-boundary exclusion matches; large
  negative penalty for semantic matches if added later.

Ordering rules:

1. Apply exclusions first.
2. If the prompt names a topic, query relevance dominates stored interests.
3. Enforce `max_per_topic` after scoring to avoid repeated banana-style saturation.
4. Fill the discovery bucket by recency and source diversity, not by preference score.
5. If there are fewer than `min_preferences` include signals and the query is broad,
   fall back to recency plus discovery.

---

## Agent Behavior

The news agent should distinguish three user intents:

- **Headlines:** fetch and summarize articles.
- **Preference management:** acknowledge, store or rely on memory extraction, and explain
  the future effect.
- **Memory inspection:** do not answer from the headline tool. Route or respond with
  the relevant stored preference facts only if present in context.

The news prompt should explicitly say:

```text
Do not infer that a user wants more coverage of a topic just because they ask why it was shown.
Treat "why did you show X?", "stop showing X", and "show me the fact for X" as diagnostics
or preference management, not positive interest.
```

---

## Configuration

```yaml
news:
  personalization:
    enabled: true
    explore_ratio: 0.2
    min_preferences: 2
    max_per_topic: 2
    candidate_multiplier: 4
    fact_days: 365
    fact_limit: 100
    min_confidence: 0.65
```

`fact_days` is intentionally longer than the old 90-day window because durable
preferences should not disappear merely because the user did not repeat them recently.
Recency still matters inside scoring, but it is not the eligibility rule.

---

## Migration Plan

1. Keep `PersonalizationContext.interest_text` temporarily for compatibility.
2. Add `preferences` and `query_text` fields.
3. Update `NewsAgent._build_personalization_ctx()` to use `NewsPreferenceBuilder`.
4. Update `get_headlines` and `NewsStore.get_personalized()` to prefer structured
   preferences when present.
5. Remove broad `list_recent_facts(days=90, limit=30)` interest concatenation once
   tests cover the new path.

No data migration is required. Existing facts remain usable if their predicates or
values match the new preference selection rules.

---

## Test Plan

### Unit Tests

- `NewsPreferenceBuilder` includes explicit news-interest facts.
- `NewsPreferenceBuilder` excludes activity and diagnostic facts.
- Negative preference parsing checks both predicate and value.
- Diagnostic prompts mentioning a topic do not create positive query preferences.
- Active goals are included at lower weight than explicit news preferences.
- Low-confidence or contradicted facts are ignored.

### Store Tests

- Excluded topics are filtered before ranking.
- Current-query relevance outranks unrelated stored interests.
- `max_per_topic` prevents more than N articles from the same topic.
- Discovery bucket is recency/source-diversity ranked, not preference ranked.
- Broad query with too few preferences falls back to recency.

### Agent Tests

- "what's in the news?" uses stored news preferences.
- "tech headlines" does not over-rank bananas from memory.
- "why do you keep suggesting bananas?" does not call `get_headlines`.
- "stop showing bananas" results in an exclusion signal being respected on the next
  headline request.
- "show me the fact that says I like bananas" answers with the supporting memory fact
  or says no such fact is present, without substituting an unrelated fact.

---

## Open Questions

- [ ] Should explicit news preferences live as regular `memory_facts` with naming
  conventions, or should memory add a first-class preference facet type?
- [ ] Should topic saturation use article tags only, or derive topics from article
  title/summary when tags are too broad?
- [ ] Should preference-management prompts create immediate write proposals, or rely on
  the existing post-turn memory extractor?
