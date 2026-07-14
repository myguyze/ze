# Internal Module Contracts

This feature has no external HTTP/WebSocket surface — it changes internal
retrieval behavior consumed by `PostgresMemoryStore.retrieve()`, already called
by the `fetch_context` graph node and directly by domain services (`GoalPlanner`,
`BaseAgent.agentic_loop`). The contracts below are the function signatures new
or changed code must satisfy so `core/ze-memory` callers, `core/ze-core`'s trace
node, and `apps/ze-web`'s Mind panel stay compatible.

## `ze_memory.relevance_config.relevance_config(settings) -> RelevanceConfig`

- Input: same `settings` object accepted by `nli_config()` today (`ZeApiSettings`
  or a raw dict).
- Output: fully populated `RelevanceConfig` (data-model.md), falling back to
  `defaults.py` constants for any missing key.
- MUST NOT raise — a malformed `memory:` config section falls back to defaults
  with a `log.warning`, matching `nli_config()`'s tolerance.

## `ze_memory.composite.composite_score(candidate, weights: CompositeWeights, now: datetime) -> float`

- Input: any of `Fact | Episode | Entity | Event` with `relevance_score` already
  populated, plus a reference "now" for recency decay.
- Output: a single float in a stable, documented range (implementation may choose
  `[0, 1]` or unbounded — MUST be internally consistent so sort order is
  deterministic per FR-010/FR-011).
- Pure function — no I/O, no exceptions raised for missing `relevance_score`
  (treat `None` as `0.0` similarity contribution, since only entity-anchor
  candidates without a vector hit should ever have `None`, and those already
  carry a `relevance_score` per data-model.md item 3).

## `ze_memory.entity_anchor.match_entities_in_query(query_text: str, pool) -> list[EntityAnchorMatch]`

- Input: raw user query text, an asyncpg pool.
- Output: word-bounded, case-insensitive matches against `memory_entities`
  canonical names and aliases; canonical-name matches win over overlapping alias
  matches (FR-005, spec Edge Cases).
- MUST return `[]` (not raise) on any DB error — entity-anchor retrieval degrades
  to vector-only silently, matching FR-016/FR-017's "recoverable via configuration"
  and general graceful-degradation posture elsewhere in `ze_memory`.

## `ze_memory.entity_anchor.fetch_anchored_candidates(matches: list[EntityAnchorMatch], graph_store: GraphStore, pool) -> MemoryContext`

- Input: matched entities, the existing `GraphStore`, pool.
- Output: a `MemoryContext` populated only with one-hop `DESCRIBES`/`MENTIONS`/
  `SOURCED_FROM` neighbours (facts, episodes, events) of the matched entities,
  each with `relevance_score = max(vector_similarity_if_known, entity_match_constant)`
  and `retrieval_provenance = "entity_anchor"` (FR-006, FR-009).
- MUST apply the same validity filters as vector candidates: `contradicted = false`,
  `episode_retrievable_sql()`, current-session exclusion (FR-007) — reuse the
  existing filter fragments from `policies.py`/`dream/retrieval.py`, do not
  reimplement them.

## `ze_memory.policies.*Policy.retrieve()` (all 11 existing classes)

- Unchanged external signature: `async def retrieve(self, request: RetrievalRequest,
  store: MemoryQueryable) -> MemoryContext`.
- New internal contract: before returning, each policy (except `MemoryUIPolicy`/
  `ProfilePolicy`) MUST:
  1. Select real similarity for every SQL-fetched candidate (research.md item 5).
  2. Merge in `fetch_anchored_candidates()` results, deduplicating by ID
     (keep max `relevance_score`, per FR-008/FR-009).
  3. Drop candidates below `relevance_config().floor` (or type override).
  4. Sort remaining candidates by `composite_score()` before calling
     `budget_facts`/`budget_episodes`/etc. (FR-010, FR-012).
  5. When `relevance_floor == 0` and composite disabled via config, produce the
     same ordering as today (FR-017 rollback path).

## `ze_memory.retrieval_rerank.live_rerank(candidates, query_text, nli_client, cfg) -> list`

- New function alongside the existing async `build_retrieval_cache`.
- Input: post-floor, post-composite-sort candidate list (already bounded to
  `cfg.live_rerank_candidate_limit`), raw query text, `NLIClient`.
- Output: re-ordered candidate list.
- MUST return the input unchanged (no reorder, no exception) if `nli_client` is
  `None`, disabled by config, over `cfg.live_rerank_timeout_ms`, or raises
  (FR-014) — call site wraps in the same `try/except` + `log.warning` pattern
  used throughout `ze_memory` (e.g. `_graph_augment`).
- MUST NOT read or write `PostgresRetrievalCacheStore` — kept independent of the
  async session-cache path (research.md item 4, spec Clarification).

## `ze_core.orchestration.nodes.trace._extract_memory_chunks(memory_context) -> list[MemoryChunkTrace]`

- Changed: `score=getattr(fact, "relevance_score", None) or 0.0` (was
  `fact.confidence`); new `extraction_confidence=getattr(fact, "confidence", None)`
  passed through separately (FR-003).
- Resolved (no new field needed): `ze_core/orchestration/nodes/context.py`'s
  `fetch_context` node always populates `memory_context` with a real
  `MemoryContext` before `capability_check`/`record_trace` run — it is never
  `None` on any path that reaches `record_trace`. So an empty `memory_chunks`
  list is already unambiguous: it means "retrieval ran and found nothing above
  the floor" (FR-004), not "retrieval did not run." No
  `memory_retrieval_ran: bool` field is required on `MessageTrace`.
