# Phase 0 Research: Memory Retrieval Relevance

All items below were resolved by reading the existing `core/ze-memory` implementation
rather than by external research — this phase extends code that already exists, and
the open questions were "how does the current system behave" rather than "what
library should we pick." No NEEDS CLARIFICATION markers remain in the Technical
Context; each item traces back either to a code reading or to a spec clarification.

## 1. Where does "extraction confidence" leak into the Mind panel today?

**Decision**: `core/ze-core/ze_core/orchestration/nodes/trace.py::_extract_memory_chunks`
sets `MemoryChunkTrace.score = getattr(fact, "confidence", 1.0)` for facts and
`getattr(ep, "relevance", 0.0)` for episodes. `Fact.confidence` is extraction
confidence (set at write time by the extractor LLM), not retrieval similarity —
this is exactly the bug FR-003/SC-003 describe. `Episode.relevance` is a stored,
LLM-scored field from a different pass (unrelated to query-time similarity either).

**Rationale**: Confirmed by reading `ze_memory/types.py` (`Fact.confidence` docstring-free
but used at write time in `extractor.py`) and `trace.py`. No existing field carries
query-time cosine similarity anywhere in the pipeline today — it is computed inside
`ORDER BY embedding <=> $1::vector` in SQL and discarded; never selected as a value.

**Alternatives considered**: Backfilling similarity from the retrieval cache
(`RetrievalCacheEntry`) — rejected, since the cache only stores ranked *IDs*, not
scores, and only exists for repeat queries in a session (see item 4).

## 2. How is the entity/relationship graph currently used in retrieval?

**Decision**: `PostgresMemoryStore._graph_augment` (`retriever.py`) runs after
`policy.retrieve()` returns, seeds a `BoundedExpansionPolicy.expand()` call from
the **already-retrieved** `ctx.entities` and `ctx.facts` IDs (i.e., only what the
vector search already found), walks one hop (`max_hops=1` by config default), and
merges newly discovered facts/entities via `graph/projection.py::enrich_context`.
This exactly matches the spec's framing: "the graph only decorates results the
vector search already picked." There is no code path today that extracts entities
from the *query text* and uses them as a traversal seed.

**Rationale**: Confirmed by reading `retriever.py:141-203` and `graph/projection.py`.
`GraphExpansion` already carries `episode_ids`, but `enrich_context` only fetches
facts and entities from it — episodes/events discovered via the graph are silently
dropped today, a gap FR-006 must close for the new entity-anchor path (though not
necessarily for the existing post-hoc decoration path, which stays as-is).

**Alternatives considered**: Extending `_graph_augment`'s existing seed set to also
include query-text entity matches — rejected in favor of a separate `entity_anchor.py`
module (see plan.md), because the existing path answers "what else relates to what
we found" while the new path answers "what does the query name directly," and their
scores mean different things (weak decoration vs. strong anchor evidence, see item 3).

## 3. How to reconcile entity-anchor "found by name" with a numeric relevance score

**Decision** (from spec Clarification, Session 2026-07-14): `score = max(vector_similarity,
entity_match_constant)`. `entity_match_constant` is a new config value in
`memory.entity_anchor.match_constant`, defaulting high enough to clear
`memory.relevance_floor` on its own. When the same fact/episode is also found by
the vector path with a higher cosine similarity, that similarity is used instead
(same "strongest evidence wins" rule FR-008 already requires for dedup — extended
here to also govern scoring, not just deduplication).

**Rationale**: Existing dedup pattern in `enrich_context` only skips IDs already in
`ctx` — it does not compare or merge scores today (there is no score to merge). This
phase introduces both the score field and the merge rule together.

## 4. How does the existing NLI rerank (phase 79/80) interact with the live turn?

**Decision**: `retrieval_rerank.py::build_retrieval_cache` already reranks **both**
facts and summaries via `NLIClient.scores()` — not summaries only, as the spec's
background section suggested — but it runs `fire_and_forget` (async, non-blocking)
*after* the response for the current turn is already built, and only benefits a
**future** query in the same session via `PostgresRetrievalCacheStore` cache hit
(`_apply_retrieval_cache`). The very first occurrence of any query gets raw ANN
order with no NLI involvement. Per spec Clarification, Story 4's live rerank is a
**separate, synchronous, uncached** call scoped to the small post-floor candidate
set (bounded by FR-015) — it does not read from or populate the async cache; the
two mechanisms coexist without interference.

**Rationale**: Confirmed by reading `retriever.py:112-157` (cache read/write around
`policy.retrieve()`) and `retrieval_rerank.py:184-245` (`build_retrieval_cache`
reranks fact_rows via `rerank_row_ids(..., "value", ...)`, not just summary rows).

**Alternatives considered**: Making the live rerank populate the cache directly so
a second identical query in-session gets the same ranking without recomputation —
rejected as unnecessary coupling; the live call is already fast enough (bounded
candidate count) that cache reuse isn't needed, and keeping the paths independent
avoids a shared-state bug surface.

## 5. Where do per-policy SQL queries need a similarity column added?

**Decision**: Every `_fetch_*_by_similarity` helper and inline query in
`policies.py` (`_fetch_facts_by_similarity`, `_fetch_entities_by_similarity`,
`_fetch_events_by_similarity`, `_fetch_calendar_events_by_similarity`,
`_fetch_session_summary_rows`, plus the ad hoc fact/episode queries inside each
of the 9 policy classes) currently does `ORDER BY embedding <=> $1::vector` without
selecting `1 - (embedding <=> $1::vector) AS similarity`. Each needs that column
added and threaded through `projection.py`'s `_*_from_row` constructors into the
new `relevance_score` field. Rows with `embedding IS NULL` (legacy rows, already
handled by a `UNION`-style fallback to recency order in several helpers) get
`relevance_score = None` and can only pass the floor via the entity-anchor path
(per spec Edge Cases).

**Rationale**: Direct reading of `policies.py` — every helper's `ORDER BY` clause
computes the distance already; PostgreSQL/pgvector does not require re-computation,
just selecting the same expression as a column.

**Alternatives considered**: Computing similarity in Python via
`consolidation_store._cosine_similarity` (already used elsewhere for write-time
contradiction checks) — rejected as slower and redundant; the database has already
computed the distance for `ORDER BY`.

## 6. Where should floor/weight config live, and what's the existing pattern to follow?

**Decision** (from spec Clarification): `config/config.yaml` under `memory:`,
following the exact pattern `nli_config.py` already establishes for NLI thresholds
— a resolver function (`relevance_config(settings)`) that reads
`settings.config["memory"]`, falls back to constants in `defaults.py`, and is
hot-reloaded on SIGHUP like the rest of `memory:`. New keys: `relevance_floor`
(global + optional per-type overrides), `composite_weights` (similarity/recency/
confidence), `entity_anchor.match_constant`, `entity_anchor.enabled`,
`live_rerank.enabled`, `live_rerank.candidate_limit`, `live_rerank.timeout_ms`.

**Rationale**: `nli_config.py` is a 5-year-stable pattern already used for
structurally identical config (thresholds affecting retrieval/write behavior);
reusing it means zero new config-loading code paths.

## 7. Word-boundary matching for entity names/aliases

**Decision**: The existing `_link_episode_entities` (`retriever.py:896-944`) matches
entity canonical names/aliases against text via SQL `position(lower(name) in text) > 0`
— a plain substring match, **not** word-bounded. The spec's edge cases explicitly
require word-bounded matching (to avoid "Al" matching inside "Sally"). The new
`entity_anchor.py` module must not reuse this SQL pattern as-is; it needs a
regex-based or `\y...\y`-bounded query (Postgres supports `~*` with `\m`/`\M` word
boundaries), or a Python-side regex check after a cheaper SQL prefilter.

**Rationale**: Direct reading of the SQL in `_link_episode_entities`. This existing
helper is used for episode→entity linking at write time, a different (lower-stakes)
use case than query-time retrieval anchoring; the new code should not inherit its
substring-match weakness silently.

## 8. Graph traversal depth for entity anchors

**Decision** (from spec Clarification): One hop only, via the existing
`GraphStore.expand(seed_ids, max_hops=1)` — the same primitive
`BoundedExpansionPolicy` already uses for post-hoc decoration, just called with a
different seed set (matched entity IDs, not already-retrieved candidate IDs).

**Rationale**: `GraphStore.expand()` already supports an arbitrary `max_hops`
parameter; no new traversal code is needed, only a new caller.

## 9. Scope across retrieval policies

**Decision** (from spec Clarification): All 9 orchestration-level policies plus
`PlannerPolicy` and `ToolExecutorPolicy` (domain-service-level) get the full stack
— floor, entity-anchor, composite ranking, and (where token/latency budgets allow)
live rerank. `MemoryUIPolicy` and `ProfilePolicy` (introspection-only) are exempted
from the floor (they intentionally show broader context for browsing) but still
benefit from carrying the real similarity score for display accuracy.

**Rationale**: `policies.py`'s docstring already documents the two-tier
classification (orchestration-level dispatched via agent name, domain-service-level
called directly); the spec clarification confirmed FR-016 applies to both tiers.
