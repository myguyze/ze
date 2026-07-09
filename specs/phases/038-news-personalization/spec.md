# News Personalization — Spec

> **Package:** `ze-news` (scoring layer), `ze` (briefing wiring)
> **Phase:** 38
> **Status:** Done
> **Depends on:** Phase 37 ([37-news-package.md](../037-news-package/spec.md)), Phase 3 ([03-memory.md](../003-memory/spec.md)), Phase 19 ([28-goal-engine.md](../028-goal-engine/spec.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `PersonalizationContext` type | ✅ Done |
| `NewsStore.get_personalized()` | ✅ Done |
| `get_headlines` tool updated | ✅ Done |
| `NewsAgent` passes memory context | ✅ Done |
| `MorningBriefing` personalized headlines | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Phase 37 fetches and stores news from all configured sources equally. Ze has no
opinion on which articles matter to the user — it returns results by recency or
semantic query similarity, with no awareness of who the user is or what they care about.

Ze already knows the user well: user facts accumulate through conversation, active
goals reflect current focus, and memory context is injected into every agent prompt.
This phase wires that knowledge into the news layer so that Ze can surface articles
that are genuinely relevant — while preserving deliberate exposure to things outside
the user's usual interests.

The user named the core tension explicitly: pure personalization is a filter bubble.
The design therefore treats serendipity as a first-class feature, not an afterthought.
Every `get_personalized()` call produces two buckets — a relevance-ranked majority
and an intentionally off-profile minority — and Ze presents both, distinguished in
the morning briefing.

---

## Responsibilities

- Define `PersonalizationContext` — a lightweight snapshot of user facts and active
  goal titles, built at query time from the memory store.
- Add `NewsStore.get_personalized()` — scores stored articles against the user's
  interest vector, returns a ranked list split into `relevant` and `discovery` buckets.
- Update the `get_headlines` tool to optionally accept and use a personalization context.
- Update `NewsAgent` to build a `PersonalizationContext` from the memory store and
  pass it through to `get_headlines`.
- Update `MorningBriefing` to call `get_personalized()` and render the two buckets
  as distinct sections.
- Explicit preference signals ("I don't care about sports") are stored as user facts
  via the existing memory path — no new machinery required.

---

## Out of Scope

- **Engagement tracking** — no click or view log table. Implicit signals (user asked
  about an article) are captured through the existing memory system when they naturally
  arise in conversation, not by instrumenting every fetch.
- **Source-level weighting** — Ze does not up/down-rank entire sources. Article-level
  scoring is sufficient and avoids penalising a source for one bad article.
- **Preference model training** — no embeddings stored per article view, no
  collaborative filtering, no ML training loop. Cosine similarity against a live
  memory snapshot is the entire model.
- **User-facing feedback UI** — no thumbs-up/down buttons or explicit rating flow.
  Natural conversation is the feedback mechanism: "Ze, I don't care about football"
  → stored as user fact → filtered on next run.
- **Negative filtering** — excluded topics ("no sports") are stored as user facts and
  passed as exclusion keywords in `PersonalizationContext`. Simple keyword matching
  at score time; no semantic exclusion classifier.

---

## Module Location

No new files. Changes to existing modules only:

```
packages/ze-news/
  ze_news/
    types.py        ← add PersonalizationContext dataclass
    store.py        ← add get_personalized(), _score_articles()
    agents/
      tools.py      ← update get_headlines signature
      agent.py      ← build PersonalizationContext from memory, pass to tool

packages/ze/
  ze/
    jobs/
      briefing.py   ← use get_personalized(), render two sections
```

---

## Data Structures

```python
# ze_news/types.py

@dataclass
class PersonalizationContext:
    interest_text: str          # concatenated user facts + goal titles
    exclusions: list[str]       # topics the user explicitly doesn't want
    explore_ratio: float = 0.2  # fraction of results that are serendipitous
    fact_count: int = 0         # number of non-exclusion facts; used for min_facts check
```

`interest_text` is built by the caller (the agent or briefing job) from live memory
at query time — it is never stored. It is a plain string, not a pre-computed embedding,
so the store can embed it fresh on each call using the shared
`paraphrase-multilingual-MiniLM-L12-v2` singleton. This keeps the store stateless with respect to user data.

---

## Scoring Layer

### `NewsStore.get_personalized()`

```python
async def get_personalized(
    self,
    ctx: PersonalizationContext,
    limit: int = 20,
    tags: list[str] | None = None,
) -> tuple[list[Article], list[Article]]:
    """
    Returns (relevant, discovery) where:
      - relevant: top (1 - explore_ratio) * limit articles ranked by interest score
      - discovery: remaining articles ranked by recency, not by interest score
    Never raises. Falls back to get_recent() if ctx.interest_text is empty.
    """
```

#### Algorithm

1. Fetch `limit * 3` recent candidates from Postgres (optionally filtered by tags),
   ordered by `published_at DESC`. Over-fetching gives the scorer enough material to
   fill both buckets after filtering exclusions.
2. Embed `ctx.interest_text` → `interest_vec` (384-dim).
3. For each candidate: compute `cosine_similarity(article.embedding, interest_vec)`.
   Articles without an embedding get score 0.0.
4. Filter out candidates whose title or summary contains any term from `ctx.exclusions`
   (case-insensitive substring match).
5. Sort by score descending.
6. Split:
   - `n_relevant = ceil((1 - ctx.explore_ratio) * limit)`
   - `relevant` = top `n_relevant` by score
   - `discovery` = next `limit - n_relevant` by recency (re-sorted by `published_at`)
7. Return `(relevant, discovery)`.

The discovery bucket is intentionally **not** ranked by interest score — it is ranked
by recency. This ensures the user sees genuinely fresh, off-profile content rather than
the least-bad personalized results.

#### Fallback

If `ctx.interest_text` is empty or blank, **or** if the caller signals fewer than
`min_facts` non-exclusion facts (configurable, default 5), `get_personalized()` calls
`get_recent()` and returns `(articles, [])`. This covers:
- First-run: Ze has no user facts yet.
- Low-signal: 1–3 facts produce noisy cosine similarities, not meaningful preference ranking.

---

## Building `PersonalizationContext`

Context is built by the caller, not the store.

### In `NewsAgent`

The agent has access to `memory_store` via `config["configurable"]`. Before calling
`get_headlines`, it fetches a snapshot:

```python
async def _build_ctx(self, memory_store, goal_store) -> PersonalizationContext:
    facts = await memory_store.list_recent_facts(days=90, limit=30)
    goals = await goal_store.list_active_goal_titles()
    _exclusion_keys = ("not interested", "don't like", "avoid", "no ")
    exclusions = [
        f.value for f in facts
        if any(kw in f.key.lower() for kw in _exclusion_keys)
    ]
    topic_facts = [f for f in facts if f not in exclusions]
    interest_parts = [f"{f.key}: {f.value}" for f in topic_facts]
    interest_parts += goals
    return PersonalizationContext(
        interest_text=" | ".join(interest_parts),
        exclusions=exclusions,
        fact_count=len(topic_facts),
    )
```

The agent builds this once per turn and passes it to the tool via a turn-scoped
variable (same pattern as other context injection in Ze). Both `memory_store` and
`goal_store` are available via `config["configurable"]`.

### In `MorningBriefing`

The briefing job receives both `memory_store` and `goal_store` via constructor
injection (same as other briefing dependencies). It builds `PersonalizationContext`
the same way at run time and passes it to `get_personalized()`.

---

## Updated Tool Signature

```python
# ze_news/agents/tools.py

@tool(access=ToolAccess.READ, description="...")
async def get_headlines(
    news_store: NewsStore,
    limit: int = 20,
    tags: list[str] | None = None,
    personalized: bool = True,        # new: use personalization if context available
) -> dict:                            # returns {"relevant": [...], "discovery": [...]}
```

The tool returns a dict with two keys so the agent can present them distinctly in its
response. When `personalized=False` or no context is available, `discovery` is empty
and `relevant` contains the plain recency-ordered list (backward-compatible).

---

## Morning Briefing Integration

```
📰 For you:
  • [relevant article 1] (source)
  • [relevant article 2] (source)
  ...

🔭 Outside your usual:
  • [discovery article 1] (source)
  • [discovery article 2] (source)
```

The "Outside your usual" section is always present when `explore_ratio > 0` and the
store has enough articles. This makes the serendipity intention explicit to the user
rather than hiding it in a black-box ranking.

---

## Preference Signal Flow

No new code path for preference capture. The existing flow:

1. User says "I don't care about football" in conversation
2. Memory system stores `UserFact(key="not interested in", value="football")`
3. Next time `_build_ctx()` runs, "football" appears in `exclusions`
4. Articles mentioning "football" are filtered out of both buckets

This is deliberately simple. Semantic exclusion (embedding-distance-based filtering)
is more powerful but risks over-filtering related topics. Keyword exclusion is
transparent and reversible: "Ze, you can show me football news again" removes the fact.

---

## Configuration

```yaml
# config/config.yaml

news:
  personalization:
    enabled: true
    explore_ratio: 0.2        # 20% discovery, 80% relevant
    candidate_multiplier: 3   # fetch limit * 3 candidates before scoring
    briefing_limit: 8         # total headlines in briefing (up from 5)
    min_facts: 5              # minimum user facts to enable scoring; below this, fall back to recency
```

`briefing_limit` must be **8** (not 5) for the explore/exploit split to produce ≥2 discovery
articles. At `briefing_limit=5`, `ceil(0.2 × 5) = 1` — a single discovery article is not
meaningful serendipity.

`explore_ratio` is user-tunable. `0.0` = fully personalized (filter bubble, not
recommended). `1.0` = no personalization (equivalent to current behaviour).

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.memory.postgres.PostgresMemoryStore` | `list_recent_facts()` — build interest text |
| `ze_core.embeddings.get_embedder` | Embed `interest_text` at query time |
| `ze_news.store.NewsStore` | New `get_personalized()` method |
| `ze_news.types.PersonalizationContext` | New dataclass |

`ze-news` does not gain a direct dependency on `ze_core.memory` — the context is
built by the caller (agent or briefing job) and passed in as a plain dataclass.
`ze-news` only sees `PersonalizationContext.interest_text` as a string to embed.
This preserves the package boundary: `ze-news → ze-core` only.

---

## Implementation Notes

- **Why cosine similarity and not pgvector `<=>` for scoring?** The interest vector
  is computed at query time for a single user context string. There is no way to
  push this into a SQL `ORDER BY` without a parameterised vector query. The candidate
  set is small (`limit * 3`, typically 60–100 rows), so Python-side scoring is fast
  enough and avoids a more complex SQL query.
- **Why over-fetch by 3×?** Exclusion filtering removes an unknown number of candidates.
  3× provides headroom without loading the full table. If the filtered set is still
  smaller than `limit`, `get_personalized()` returns whatever is available.
- **Why string concatenation for `interest_text`?** Embedding a single concatenated
  string is one model call. Embedding each fact separately and averaging would be
  more precise but adds latency proportional to fact count. The concatenation
  approximation is good enough for a 384-dim space with 30 facts.
- **First-run experience / `min_facts` threshold.** `get_personalized()` checks the
  number of non-exclusion facts before scoring. Below `min_facts` (default 5), it
  falls back to `get_recent()` even when `interest_text` is non-empty. This avoids
  noise-driven "personalization" when Ze has only 1–3 facts — at that scale, cosine
  similarities are random, not signal.
- **`explore_ratio` is per-call, not global.** The briefing and the agent tool can use
  different ratios — the briefing might use 0.2 while an explicit "show me headlines"
  query uses 0.0 (pure relevance). Pass it via `PersonalizationContext` so callers
  control it.
- **Multilingual embedding.** Ze uses `paraphrase-multilingual-MiniLM-L12-v2` (384-dim,
  same pgvector schema). This model handles Portuguese and English content in the same
  embedding space, making cosine similarity meaningful for local PT sources. Migration
  `zc010` NULLs stale embeddings computed with the old `all-MiniLM-L6-v2` model.
- **Personalization indicator in briefing.** When `get_personalized()` is used (not
  the fallback path), the briefing header should say *"📰 For you (based on your
  interests):"* rather than *"📰 Headlines:"*. One line — makes the feature visible
  without requiring explanation.
- **Exclusion word-boundary matching.** Exclusion terms from `PersonalizationContext`
  should be matched with word boundaries (`re.search(r'\b' + re.escape(term) + r'\b',
  text, re.IGNORECASE)`) to avoid false positives ("sport" matching "transport").
- **`goal_store` in `MorningBriefing`.** The briefing job must receive `goal_store`
  via constructor injection to build a complete `PersonalizationContext`. Wire it in
  `ze/container.py` alongside `memory_store`.

---

## Open Questions

All questions resolved. See the pre-mortem risk analysis (not committed) for full detail.

- [x] **Should exclusions use keyword matching or semantic filtering?** → Keyword
  matching with word-boundary regex. Transparent, reversible, avoids false positives
  like "sport" matching "transport". Revisit if users report over-filtering.
- [x] **Should `interest_text` embed goals or just user facts?** → Both. Active goal
  titles are high-signal (the user is actively working on them) and short enough to
  include without overwhelming the fact context.
- [x] **Where does `memory_store` come from inside the news tool?** → The tool
  cannot take `memory_store` as a direct parameter without making `ze-news` depend
  on `ze-core.memory`. Instead, `NewsAgent` builds `PersonalizationContext` before
  calling the tool, and the tool receives only the context. The context is passed
  via a turn-scoped mechanism (agent builds it and injects via tool arguments).
- [x] **What is the `explore_ratio` default?** → 0.2. One in five headlines is
  off-profile. Enough to surface genuine surprises without overwhelming the user.
  Configurable in `config.yaml`. `briefing_limit` must be ≥8 for this to produce
  ≥2 discovery articles.
- [x] **Should `list_active_goals_titles()` come from `memory_store` or `goal_store`?**
  → `goal_store`. `GoalStore.list_active_goal_titles()` exists; `goal_store` is already
  in `config["configurable"]` for agents, and must be passed to `MorningBriefing` via
  constructor injection. Using `goal_store` is more accurate (structured data) and
  avoids an extra memory query.
- [x] **`list_recent_facts` call signature?** → `list_recent_facts(days=90, limit=30)`.
  The actual `PostgresMemoryStore` signature requires both `days` and `limit`. 90 days
  captures established interests; limit=30 gives enough material without overwhelming
  the interest vector.
