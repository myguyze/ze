---

description: "Task list for Memory Retrieval Relevance (phase 106)"
---

# Tasks: Memory Retrieval Relevance

**Input**: Design documents from `/specs/phases/106-memory-retrieval-relevance/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — constitution principle V (Test Discipline) is non-negotiable
for this repo; every new module and every changed policy gets unit tests with
mocked asyncpg pools (`AsyncMock`) and a mocked `NLIClient`, no real DB/LLM calls.

**Organization**: Tasks are grouped by user story (spec.md priorities: US1=P1,
US2=P2, US3=P2, US4=P3) so each can be delivered and validated independently.
No new database tables/migrations exist in this feature — all new state is
transient dataclass fields or config.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependencies)
- **[Story]**: US1 / US2 / US3 / US4
- File paths are relative to repo root

---

## Phase 1: Setup

**Purpose**: Config scaffolding shared by every story — no story-specific logic yet.

- [X] T001 [P] Add new constants to `core/ze-memory/ze_memory/defaults.py`: `RELEVANCE_FLOOR_DEFAULT`, `COMPOSITE_WEIGHT_SIMILARITY_DEFAULT`, `COMPOSITE_WEIGHT_RECENCY_DEFAULT`, `COMPOSITE_WEIGHT_CONFIDENCE_DEFAULT`, `ENTITY_MATCH_CONSTANT_DEFAULT`, `ENTITY_ANCHOR_ENABLED_DEFAULT`, `LIVE_RERANK_ENABLED_DEFAULT`, `LIVE_RERANK_CANDIDATE_LIMIT_DEFAULT`, `LIVE_RERANK_TIMEOUT_MS_DEFAULT`
- [X] T002 [P] Add `memory.relevance_floor`, `memory.relevance_floor_overrides`, `memory.composite_weights`, `memory.entity_anchor`, `memory.live_rerank` keys with illustrative defaults to `apps/ze-api/config/config.yaml` (see data-model.md config schema)

**Checkpoint**: Config keys exist and resolve to defaults; nothing reads them yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types and config resolver every user story's code depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 [P] Add `relevance_score: float | None = None` and `retrieval_provenance: str | None = None` fields to `Fact`, `Episode`, `Entity`, `Event` dataclasses, and `relevance_score: float | None = None` to `SessionSummary`, in `core/ze-memory/ze_memory/types.py`
- [X] T004 [P] Create `RelevanceConfig` and `CompositeWeights` dataclasses in `core/ze-memory/ze_memory/relevance_config.py`
- [X] T005 [US-shared] Implement `relevance_config(settings) -> RelevanceConfig` resolver in `core/ze-memory/ze_memory/relevance_config.py`, mirroring the `nli_config()` pattern in `core/ze-memory/ze_memory/nli_config.py` (reads `settings.config["memory"]`, falls back to T001's defaults, never raises) (depends on T001, T004)
- [X] T006 [P] Unit tests for `relevance_config()` in `core/ze-memory/tests/test_relevance_config.py` — default fallback, YAML override, malformed-config tolerance (depends on T005)
- [X] T007 Update `_fact_from_row`, `_episode_from_row`, `_entity_from_row`, `_event_from_row`, `_session_summary_from_row` in `core/ze-memory/ze_memory/projection.py` to read an optional `similarity` column from the row into `relevance_score` when present (depends on T003)

**Checkpoint**: `RelevanceConfig` resolvable from settings; dataclasses can carry a score; nothing populates it from SQL yet outside this phase's plumbing.

---

## Phase 3: User Story 1 - Irrelevant memories stay out of context (Priority: P1) 🎯 MVP

**Goal**: Every similarity-based lookup returns a real relevance score; candidates
below a configurable floor are excluded from context; the Mind panel shows
relevance, not extraction confidence; empty results are distinguishable from
"did not run."

**Independent Test**: Ask a question matching no stored memory — confirm the
delivered memory block is empty and the Mind panel says so; ask a question with
a genuinely relevant fact — confirm it's retrieved with its real relevance score
shown (not `confidence`).

### Tests for User Story 1

- [X] T008 [US1] Unit test: SQL similarity column present and correctly mapped to `relevance_score` for facts/entities/events/session-summaries in `core/ze-memory/tests/test_relevance_floor.py`
- [X] T009 [US1] Unit test: candidates below `relevance_floor` (and per-type override) are excluded from `MemoryContext` for `CompanionPolicy`/`ResearchPolicy`, in the same `core/ze-memory/tests/test_relevance_floor.py` as T008 (same file — write together, not in parallel)
- [X] T010 [US1] Unit test: `relevance_floor = 0` reproduces pre-phase-106 ordering (FR-017 rollback), in the same `core/ze-memory/tests/test_relevance_floor.py` as T008/T009
- [X] T011 [P] [US1] Unit test: `_extract_memory_chunks` sets `score` from `relevance_score` and `extraction_confidence` from `fact.confidence` separately, in `core/ze-core/tests/test_trace_memory_chunks.py` (parallel with T008-T010 — different file)
- [X] T012 [US1] Unit test: `record_trace` always produces a `MessageTrace` whenever `envelope` is present, with empty `memory_chunks` (not a missing trace) distinguishing "ran, found nothing" from "did not run" — `fetch_context` always populates `memory_context` before `record_trace` runs (confirmed via `ze_core/orchestration/nodes/context.py`), so no new boolean field is needed; empty `memory_chunks` is already unambiguous. Same file as T011 — write together, not in parallel.

### Implementation for User Story 1

- [X] T013 [US1] Add `1 - (embedding <=> $1::vector) AS similarity` to every fetch helper in `core/ze-memory/ze_memory/policies.py`: `_fetch_facts_by_similarity`, `_fetch_entities_by_similarity`, `_fetch_events_by_similarity`, `_fetch_calendar_events_by_similarity`, `_fetch_session_summary_rows`; rows from the `embedding IS NULL` fallback branches get `similarity = NULL` (depends on T007)
- [X] T014 [US1] Add the same `similarity` column to the inline fact/episode SQL blocks inside `CompanionPolicy`, `ResearchPolicy`, `EmailPolicy`, `ProspectingPolicy`, `GoalsPolicy`, `WorkflowPolicy`, `CalendarPolicy`, `RemindersPolicy`, `PlannerPolicy`, `ToolExecutorPolicy` in `core/ze-memory/ze_memory/policies.py` (depends on T013)
- [X] T015 [US1] Add a shared `apply_relevance_floor(rows, memory_type, cfg) -> list` helper to `core/ze-memory/ze_memory/policies.py` that drops rows whose `similarity` is below `cfg.floor_overrides.get(memory_type, cfg.floor)`, treating `NULL` similarity as "not eligible outside the entity-anchor path" (depends on T005, T013)
- [X] T016 [US1] Call `apply_relevance_floor()` for every fetched row set inside all 11 policy classes' `retrieve()` methods in `core/ze-memory/ze_memory/policies.py`, except `MemoryUIPolicy`/`ProfilePolicy` which are exempted per FR-016 scope decision (depends on T015)
- [X] T017 [US1] Update `_extract_memory_chunks` in `core/ze-core/ze_core/orchestration/nodes/trace.py` to set `score=getattr(fact, "relevance_score", None) or 0.0` and pass `extraction_confidence=getattr(fact, "confidence", None)` (depends on T003)
- [X] T018 [US1] Add `extraction_confidence: float | None = None` field to `MemoryChunkTrace` in `core/ze-core/ze_core/conversation/messages/types.py`
- [X] T019 [US1] Ensure `record_trace` in `core/ze-core/ze_core/orchestration/nodes/trace.py` always returns a `MessageTrace` (with empty `memory_chunks`) when `memory_context` is not `None` but has no chunks clearing the floor, so "ran, found nothing" is distinguishable from "did not run" (FR-004) (depends on T017)
- [X] T020 [US1] Update `apps/ze-web/src/widgets/trace-panel/ui/TraceEntry.tsx` to display `relevance_score`/`score` as "Relevance" and `extraction_confidence` (when present) as a distinctly labelled "Extraction confidence"
- [X] T021 [US1] Add a "no relevant memories found" empty state to `apps/ze-web/src/widgets/trace-panel/ui/TraceEmptyState.tsx` (or equivalent) distinguishing it from "retrieval did not run"
- [X] T022 [US1] Regenerate `@ze/client` SDK types (`packages/ze-client/src/generated/*`) after the `MemoryChunkTrace` schema change, per repo's codegen flow (phase 72)

**Checkpoint**: User Story 1 fully functional — floor + honest scores work end-to-end, independently testable via `eval/run.py --tag memory-relevance-floor`.

---

## Phase 4: User Story 2 - Entity-named memories are found by name (Priority: P2)

**Goal**: Query-text entity mentions become a first-class retrieval entry point:
matched entities pull their one-hop graph neighbourhood into the candidate pool
before budgeting, merged and deduplicated with vector candidates.

**Independent Test**: Store a fact linked to a named entity; ask about it by
alias with dissimilar phrasing; confirm the fact is retrieved with
`retrieval_provenance == "entity_anchor"`.

### Tests for User Story 2

- [X] T023 [US2] Unit test: `match_entities_in_query()` is word-bounded, case-insensitive, and prefers canonical-name matches over overlapping alias matches, in `core/ze-memory/tests/test_entity_anchor.py`
- [X] T024 [US2] Unit test: `fetch_anchored_candidates()` returns one-hop `DESCRIBES`/`MENTIONS`/`SOURCED_FROM` neighbours only, applies the same validity filters as vector candidates (`contradicted = false`, `episode_retrievable_sql()`, current-session exclusion), in the same `core/ze-memory/tests/test_entity_anchor.py` as T023 (same file — write together, not in parallel)
- [X] T025 [US2] Unit test: `score = max(vector_similarity, entity_match_constant)` and dedup keeps the strongest evidence when a candidate is found by both paths, in the same `core/ze-memory/tests/test_entity_anchor.py` as T023/T024
- [X] T026 [US2] Unit test: a query mentioning no known entity behaves identically to vector-only retrieval (no errors, no spurious matches), in the same `core/ze-memory/tests/test_entity_anchor.py` as T023-T025

### Implementation for User Story 2

- [X] T027 [US2] Create `EntityAnchorMatch` dataclass in `core/ze-memory/ze_memory/entity_anchor.py`
- [X] T028 [US2] Implement `match_entities_in_query(query_text, pool) -> list[EntityAnchorMatch]` in `core/ze-memory/ze_memory/entity_anchor.py` using a word-bounded (`\m`/`\M` or regex) case-insensitive match against `memory_entities.canonical_name`/`aliases` — do not reuse the plain-substring `position()` pattern from `_link_episode_entities` (depends on T027)
- [X] T029 [US2] Implement `fetch_anchored_candidates(matches, graph_store, pool, cfg) -> MemoryContext` in `core/ze-memory/ze_memory/entity_anchor.py`, calling `GraphStore.expand(seed_ids, max_hops=1)` on matched entity IDs, fetching facts/episodes/events from the expansion (extending `graph/projection.py::enrich_context`'s pattern to also cover episodes, which it currently drops), applying `contradicted`/`episode_retrievable_sql()`/current-session filters, and setting `relevance_score = max(vector_similarity_if_known, cfg.entity_match_constant)` + `retrieval_provenance = "entity_anchor"` (depends on T028, T005)
- [X] T030 [US2] Add a `merge_candidates(vector_ctx, anchor_ctx) -> MemoryContext` helper (dedup by ID, keep max `relevance_score`, prefer the winning path's `retrieval_provenance`) in `core/ze-memory/ze_memory/entity_anchor.py` (depends on T029)
- [X] T031 [US2] Wire `match_entities_in_query()` + `fetch_anchored_candidates()` + `merge_candidates()` into `CompanionPolicy`, `ResearchPolicy`, `EmailPolicy`, `ProspectingPolicy`, `GoalsPolicy`, `WorkflowPolicy`, `CalendarPolicy`, `RemindersPolicy`, `PlannerPolicy`, `ToolExecutorPolicy` in `core/ze-memory/ze_memory/policies.py`, gated by `cfg.entity_anchor_enabled` (depends on T030, T016)
- [X] T032 [US2] Wrap the entity-anchor call site in try/except with `log.warning` graceful degradation to vector-only, matching the existing `_graph_augment` pattern in `core/ze-memory/ze_memory/retriever.py` (depends on T031)

**Checkpoint**: User Stories 1 AND 2 both work independently; entity-anchor validated via `eval/run.py --tag memory-entity-anchor`.

---

## Phase 5: User Story 3 - Best memories win the token budget (Priority: P2)

**Goal**: Candidates are ordered by a composite score (similarity × recency ×
confidence) before token budgeting, not raw ANN/arrival order.

**Independent Test**: Construct a corpus where an old low-confidence fact is
marginally nearer the query than a recent high-confidence fact, with a budget
admitting only one — confirm the recent high-confidence fact wins.

### Tests for User Story 3

- [X] T033 [US3] Unit test: `composite_score()` favors recency when similarity is comparable, favors confidence when similarity and recency are comparable, in `core/ze-memory/tests/test_composite.py`
- [X] T034 [US3] Unit test: composite ordering is deterministic and reproducible from stored per-candidate component scores, in the same `core/ze-memory/tests/test_composite.py` as T033 (same file — write together, not in parallel)
- [X] T035 [US3] Unit test: `composite_weights` disabled/zeroed reproduces pure-relevance ordering (part of FR-017 rollback), in the same `core/ze-memory/tests/test_composite.py` as T033/T034

### Implementation for User Story 3

- [X] T036 [US3] Implement `composite_score(candidate, weights, now) -> float` and a recency-decay helper in `core/ze-memory/ze_memory/composite.py` (depends on T004)
- [X] T037 [US3] Sort merged candidates (vector + entity-anchor) by `composite_score()` before calling `budget_facts`/`budget_episodes`/etc. in all 11 policy classes in `core/ze-memory/ze_memory/policies.py` (depends on T036, T031)
- [X] T038 [US3] Log each candidate's similarity/recency/confidence component breakdown (structlog, `get_logger(__name__)`) at debug level for tuning inspectability (FR-011), in `core/ze-memory/ze_memory/composite.py`

**Checkpoint**: All three of US1–US3 independently functional; token budget now favors composite-best candidates.

---

## Phase 6: User Story 4 - Semantic false positives are filtered before the agent sees them (Priority: P3)

**Goal**: The existing NLI cross-encoder reranks fact candidates synchronously
in the live turn (not only asynchronously, cached for a session's next query),
gated by config, with graceful degradation on timeout/error/disable.

**Independent Test**: Craft a query, a distractor fact that clears the floor but
is topically adjacent, and a genuinely relevant fact ranked lower by raw
similarity — confirm the rerank places the relevant fact above the distractor
on the very first turn.

### Tests for User Story 4

- [X] T039 [US4] Unit test: `live_rerank()` reorders a bounded candidate set via a mocked `NLIClient`, in `core/ze-memory/tests/test_live_rerank.py`
- [X] T040 [US4] Unit test: `live_rerank()` returns input unchanged (no exception) when `nli_client is None`, disabled by config, over `timeout_ms`, or the client raises, in the same `core/ze-memory/tests/test_live_rerank.py` as T039 (same file — write together, not in parallel)
- [X] T041 [US4] Unit test: `live_rerank()` does not read from or write to `PostgresRetrievalCacheStore` (independent of the async session-cache path), in the same `core/ze-memory/tests/test_live_rerank.py` as T039/T040

### Implementation for User Story 4

- [X] T042 [US4] Implement `live_rerank(candidates, query_text, nli_client, cfg) -> list` in `core/ze-memory/ze_memory/retrieval_rerank.py`, bounded to `cfg.live_rerank_candidate_limit`, wrapped with an `asyncio.wait_for(..., timeout=cfg.live_rerank_timeout_ms / 1000)` and try/except returning the unmodified input on any failure (depends on T005)
- [X] T043 [US4] Call `live_rerank()` on the post-floor, post-composite-sort fact candidates inside `PostgresMemoryStore.retrieve()` in `core/ze-memory/ze_memory/retriever.py`, gated by `cfg.live_rerank_enabled`, after `policy.retrieve()` returns and before the existing `_graph_augment`/retrieval-cache steps (depends on T042, T037)

**Checkpoint**: All four user stories independently functional and composable.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Rollout validation, eval coverage, and Definition-of-Done items.

- [X] T044 [P] Add eval scenarios for SC-001 (no genuinely relevant memory ⇒ empty context) and SC-002 (entity-named, dissimilar-phrasing retrieval) in `eval/scenarios/`
- [X] T045 [P] Add an eval scenario asserting no regression against the existing suite with new defaults enabled (SC-004) in `eval/scenarios/`
- [ ] T045a [P] Add token-count instrumentation to eval result output (per-turn `MemoryContext.token_estimate`) needed by T047a (SC-006), in `eval/run.py` or `eval/results/` reporting
- [ ] T046 Run `python eval/run.py` baseline (all four features disabled per FR-017 config) vs. defaults-enabled and compare median added latency against SC-005 (< 150ms rerank-on, < 30ms rerank-off)
- [ ] T047 Run `quickstart.md` end-to-end (all four story validations + rollback verification)
- [ ] T047a Compare average `MemoryContext.token_estimate` (or trace-level token counts) per turn across the eval suite between the FR-017 rollback baseline and defaults-enabled, confirming an expected ≥30% reduction without SC-004 regressing (SC-006); record the comparison in `eval/results/`
- [X] T048 Update `specs/README.md` phase-106 status row and this spec's `Status` header field to `Implemented` in the same commit as the rest of this phase's changes, per constitution Principle I
- [X] T049 `make test-memory && make test-core && make test-web && make lint` all green

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (T001 for defaults) — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; its policy-wiring tasks (T031) depend on US1's floor-wiring (T016) landing in the same file (`policies.py`) first to avoid rework, but the entity-anchor module itself (T027–T030) can be built in parallel with US1.
- **User Story 3 (Phase 5)**: Its sort step (T037) depends on US2's merge step (T031) since it sorts the merged candidate pool — build `composite.py` (T036) in parallel with US1/US2, wire it in after US2 lands.
- **User Story 4 (Phase 6)**: Depends on US3's sorted, bounded candidate list (T037) as its input.
- **Polish (Phase 7)**: Depends on all four stories.

Note: because US2/US3/US4 each add one more transformation to the same
per-policy pipeline in `policies.py`/`retriever.py`, they are naturally
sequential in integration even though their core modules (`entity_anchor.py`,
`composite.py`, `retrieval_rerank.live_rerank`) can be developed and unit-tested
in parallel. Each story is still independently *testable* — via config flags
(`entity_anchor.enabled`, composite weights, `live_rerank.enabled`) — even
though final wiring order matters.

### Parallel Opportunities

- T001/T002 (Setup) in parallel — different files (`defaults.py`, `config.yaml`).
- T003/T004 (Foundational dataclass + config dataclass) in parallel; T006 after T005.
- Within each story, only test tasks that target *different* files are marked [P] (e.g., T011 vs. T008-T010 — different test files). Test tasks sharing one file (e.g., T008-T010, all in `test_relevance_floor.py`) are unmarked and meant to be written together in one pass, not literally in parallel.
- `entity_anchor.py` (US2 core module, T027–T030), `composite.py` (US3 core module, T036), and `retrieval_rerank.live_rerank` (US4 core module, T042) can all be implemented in parallel by different developers once Foundational is done — only the final wiring into `policies.py`/`retriever.py` must be sequenced.
- T044/T045/T045a (eval scenarios + instrumentation) in parallel — different concerns, though T045a may share a file with T044/T045 depending on where eval reporting lives; verify before parallelizing.

---

## Parallel Example: Foundational Phase

```bash
Task: "Add relevance_score/retrieval_provenance fields to types.py"
Task: "Create RelevanceConfig and CompositeWeights dataclasses in relevance_config.py"
```

## Parallel Example: Core Modules (post-Foundational)

```bash
Task: "Implement match_entities_in_query + fetch_anchored_candidates in entity_anchor.py"
Task: "Implement composite_score in composite.py"
Task: "Implement live_rerank in retrieval_rerank.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) + Phase 2 (Foundational).
2. Complete Phase 3 (User Story 1): real relevance scores everywhere, floor
   applied, honest Mind panel labelling.
3. **STOP and VALIDATE**: `eval/run.py --tag memory-relevance-floor`, manual
   Mind-panel check in the web client.
4. This alone satisfies SC-001, SC-003 and most of SC-006 — ship it before
   moving to entity-anchoring.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → floor + honest scores → validate → this is the MVP.
3. US2 → entity-anchored retrieval merged in → validate independently via
   `entity_anchor.enabled: false` A/B.
4. US3 → composite ranking replaces raw order → validate via zeroed weights A/B.
5. US4 → live rerank → validate via `live_rerank.enabled: false` A/B and a
   forced-timeout test.
6. Polish → eval coverage, latency check, rollback verification, docs.

---

## Notes

- No migrations in this feature — do not add an Alembic revision.
- Every new module (`relevance_config.py`, `entity_anchor.py`, `composite.py`)
  gets its own test file; no test touches a real database or a real LLM/NLI
  model (mock `NLIClient`, mock asyncpg pool, per constitution Principle V).
- FR-017's rollback config (`relevance_floor: 0`, `entity_anchor.enabled: false`,
  `live_rerank.enabled: false`) must be exercised as a test in each of US1/US2/US4
  (T010, part of T009 in spirit, T040) rather than only in the Polish phase.
- Commit after each task or logical group per repo convention.
