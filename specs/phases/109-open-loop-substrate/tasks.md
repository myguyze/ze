---

description: "Task list for Open-Loop Substrate (Phase 109, Phase A)"

---

# Tasks: Open-Loop Substrate

**Input**: Design documents from `/specs/phases/109-open-loop-substrate/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/loops-api.md, quickstart.md (all present)

**Tests**: Not explicitly requested in spec.md, but `docs/testing.md` conventions and `quickstart.md` §"Automated coverage" call for unit tests per module and one API-level integration test. Test tasks are included as part of each story's implementation (co-located, not a separate TDD gate), matching this repo's existing convention (e.g. `ze-automation/tests/`).

**Organization**: Tasks are grouped by user story (US1–US4) per spec.md priorities, after a Setup phase (new package scaffold) and a Foundational phase (schema, types, store — the shared substrate every story needs).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)

## Path Conventions

Backend-only monorepo package addition + minimal web widget, per plan.md's Project Structure:
- New core package: `core/ze-worldstate/ze_worldstate/...`, tests in `core/ze-worldstate/tests/...`
- Wiring: `apps/ze-api/ze_api/{migrate,container,compose}.py`, `apps/ze-api/ze_api/api/{schemas.py,routes/loops.py}`
- Graph substrate addition (additive only): `core/ze-memory/ze_memory/graph/{store.py,types.py}`
- Web: `apps/ze-web/src/entities/loop/...`, `apps/ze-web/src/widgets/loop-review/...`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Scaffold the new `ze-worldstate` package so it builds, is installable in the workspace, and is importable from `ze-api`.

- [ ] T001 Create `core/ze-worldstate/pyproject.toml` mirroring `core/ze-automation/pyproject.toml`'s shape (name `ze-worldstate`, deps `ze-agents`, `ze-logging`, `ze-proactive`, `ze-memory`, `ze-data`, `ze-components`, `asyncpg==0.31.0`; `[tool.uv.sources]` workspace entries; `[tool.pytest.ini_options]` `asyncio_mode = "auto"`, `testpaths = ["tests"]`; `[tool.hatch.build.targets.wheel]` `packages = ["ze_worldstate"]`)
- [ ] T002 Create package skeleton `core/ze-worldstate/ze_worldstate/__init__.py` and empty `core/ze-worldstate/tests/__init__.py`
- [ ] T003 Add `ze-worldstate` to the uv workspace members (root `pyproject.toml` / `uv.lock` regeneration) and to `apps/ze-api/pyproject.toml` dependencies, matching how `ze-automation` is registered
- [ ] T004 [P] Run `make install` to confirm the new package resolves in the workspace with no dependency errors

**Checkpoint**: `ze-worldstate` package exists, installs cleanly, has no source yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared types, errors, migration, and store that every user story's slice depends on. No user story can be implemented until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T005 [P] Define `LoopState`, `LoopClaimKind`, `LoopProvenance`, `OpenLoop` dataclasses in `core/ze-worldstate/ze_worldstate/types.py` per data-model.md (enum values fixed exactly: states `suspected`/`active`/`drifting`/`closed`/`dropped`; claim kinds `identity`/`fact`/`inference`/`suspicion`/`priority`; `OpenLoop` carries `id`, `title`, `state`, `claim_kind`, `provenance`, `confidence: float` (0.0–1.0), `goal_id: UUID | None`, `dismissed_evidence_fingerprint: str | None`, `created_at`, `updated_at`, `confirmed_at`, `closed_at`)
- [ ] T006 [P] Define `LoopNotFoundError` and `InvalidLoopTransitionError` (both `ZeError` subclasses) in `core/ze-worldstate/ze_worldstate/errors.py`
- [ ] T007 Write Alembic migration `core/ze-worldstate/ze_worldstate/migrations/versions/zw001_open_loops.py` creating the `open_loops` table per data-model.md (columns `id` UUID PK, `title` TEXT NOT NULL, `state` TEXT NOT NULL DEFAULT `'suspected'`, `claim_kind` TEXT NOT NULL, `provenance` TEXT NOT NULL, `confidence` REAL NOT NULL CHECK (0.0–1.0), `goal_id` UUID NULL FK → `goals.id` no cascade, `dismissed_evidence_fingerprint` TEXT NULL, `created_at`/`updated_at` TIMESTAMPTZ NOT NULL DEFAULT now(), `confirmed_at`/`closed_at` TIMESTAMPTZ NULL); add `depends_on` referencing the `goals` table migration
- [ ] T008 Create `core/ze-worldstate/ze_worldstate/migrations/env.py` mirroring `core/ze-automation/ze_automation/migrations/env.py` and `core/ze-worldstate/ze_worldstate/migrations/versions/__init__.py` (empty, matching `ze_automation`'s pattern)
- [ ] T009 Define `LoopStore` Protocol in `core/ze-worldstate/ze_worldstate/store.py` per contracts/loops-api.md's internal contract (`create`, `get`, `list`, `transition`, `link_entity`, `link_evidence`)
- [ ] T010 Implement `PostgresLoopStore` in `core/ze-worldstate/ze_worldstate/store.py` — `create`/`get`/`list`/`transition` against `open_loops` via `asyncpg` (`transition` implements the full Phase A matrix from data-model.md's Validation rules: `suspected → active`, `suspected → dropped`, `active → closed`, `active → dropped`, `drifting → closed`, `drifting → dropped`, setting `confirmed_at`/`closed_at` as appropriate and raising `InvalidLoopTransitionError` for anything else, e.g. `active → drifting` which Phase A never produces); `link_entity`/`link_evidence` write rows into the existing `memory_relationships` table per data-model.md's relationship shapes (loop↔entity: `source_type="entity"`, `target_type="open_loop"`, predicate `"has_open_loop"`; loop↔evidence: `source_type="open_loop"`, `target_type="fact"|"episode"`, predicate `"derived_from"`)
- [ ] T011 [P] Add `_ZE_WORLDSTATE_VERSIONS = Path(ze_worldstate.__file__).parent / "migrations" / "versions"` to `apps/ze-api/ze_api/migrate.py`, import `ze_worldstate`, and include it in `_collect_version_locations()`
- [ ] T012 [P] Write `core/ze-worldstate/tests/test_store.py` covering `PostgresLoopStore.create/get/list/transition/link_entity/link_evidence` with `AsyncMock` asyncpg pool, including every valid transition in the Phase A matrix and the disallowed-transition error path
- [ ] T013 Run `make migrate` (with `make db-up`) to apply `zw001_open_loops` and confirm the meta-runner discovers the new chain

**Checkpoint**: `open_loops` table exists, `LoopStore`/`PostgresLoopStore` work and are tested, migration wired into `ze-api`. User story implementation can now begin.

---

## Phase 3: User Story 1 - Inferred loop captured as a suspicion (Priority: P1) 🎯 MVP

**Goal**: Ze derives a candidate loop from perception (conversation/email/calendar/ingestion), creates it in `suspected` state at low confidence with honest provenance and evidence links, and takes no autonomous action on it until reviewed.

**Independent Test**: Feed a conversation turn implying a commitment; verify a `suspected` loop is created with correct provenance/evidence and appears in the review surface, with no autonomous action taken.

### Implementation for User Story 1

- [ ] T014 [P] [US1] Implement the extraction relevance gate and candidate derivation in `core/ze-worldstate/ze_worldstate/extraction.py`: `propose_loop_candidates(text, provenance, evidence_refs, llm_client, embedder, loop_store, entity_resolver) -> list[OpenLoop]` per contracts/loops-api.md's signature — conservative/relevance-gated (FR-009), returns `[]` for ordinary content, calls `ze_worldstate.matching` (see T015) before creating a new loop, and creates non-`user_declared` loops in `suspected` state at low confidence with provenance set from the actual `provenance` argument (never model narration, FR-003)
- [ ] T015 [US1] Implement `core/ze-worldstate/ze_worldstate/matching.py`: entity-overlap primary / embedding-similarity-on-title tiebreaker per research.md §5 — query existing loops sharing a resolved entity via `memory_relationships`; on zero/multiple matches, fall back to cosine similarity between candidate title and existing loop titles using the injected embedder; expose a function usable both for FR-010 (attach/strengthen existing loop) and FR-011 (recognise dismissed-then-re-implied evidence against `dropped` loops)
- [ ] T016 [US1] Wire `link_evidence` calls from `extraction.py` so every created/strengthened loop records its evidence (fact/episode) per data-model.md's Loop ↔ Evidence link, satisfying FR-001's evidence-links requirement and the review surface's "why does Ze think this?" need
- [ ] T017 [US1] Add `GET /api/v0/loops` and `GET /api/v0/loops/{loop_id}` routes in `apps/ze-api/ze_api/api/routes/loops.py` per contracts/loops-api.md (`operation_id` `listLoops`/`getLoop`, `require_api_key`, `response_model`, `summary`, `description`; `list` route's `state` query param defaults to non-terminal states `suspected`/`active`/`drifting`); add `LoopListItem`/`LoopDetail` Pydantic schemas to `apps/ze-api/ze_api/api/schemas.py`; register the router in `apps/ze-api/ze_api/api/routes/__init__.py`
- [ ] T018 [US1] Implement plain-dict service functions in `core/ze-worldstate/ze_worldstate/rest.py` (mirrors `ze_automation/rest.py`) backing the two routes from T017 — `list_loops(loop_store, states)`, `get_loop(loop_store, loop_id)` (raising `LoopNotFoundError` → 404), including evidence lookups (evidence summaries per contracts/loops-api.md's `LoopDetail.evidence`) for `get_loop`'s detail payload. **Entity lookups for `LoopDetail.entities` are added later in T037 (US3), not here** — US1's MVP does not require resolved-entity data in the response.
- [ ] T019 [US1] Implement `build_worldstate_stack(shared, settings)` in `core/ze-worldstate/ze_worldstate/bootstrap.py` mirroring `ze_automation.bootstrap.build_automation_stack` — constructs `PostgresLoopStore`, exposes it via `deps` for `container.py` wiring
- [ ] T020 [US1] Wire `build_worldstate_stack` into `apps/ze-api/ze_api/container.py` (import, call, `shared.dep_map.update(worldstate.deps)`) the same way `automation` is wired
- [ ] T021 [US1] Invoke `ze_worldstate.extraction.propose_loop_candidates` from the existing conversation-turn processing path (the same point that already writes facts/episodes for a conversation inflow) so User Story 1's acceptance scenario ("I really need to renew my passport before the trip" → suspected loop) is satisfiable end-to-end; this is FR-017's direct-write proto-contribution — a plain function call, no new seam
- [ ] T022 [US1] Invoke `ze_worldstate.extraction.propose_loop_candidates` (provenance `"email"`) from `ze-messenger`'s inbound message processing path (`InboundMessageProcessor`, the same point that already writes facts/episodes for an inbound email/messenger thread), satisfying FR-008's email/messenger inflow
- [ ] T023 [US1] Invoke `ze_worldstate.extraction.propose_loop_candidates` (provenance `"calendar"`) from `ze-calendar`'s sync path (the same point that already writes facts/episodes for calendar sync), satisfying FR-008's calendar inflow
- [ ] T024 [US1] Invoke `ze_worldstate.extraction.propose_loop_candidates` (provenance `"ingestion"`) from the ingestion pipeline's write path (the same point that already writes facts/episodes for an ingested document), satisfying FR-008's ingestion inflow
- [ ] T025 [P] [US1] Write `core/ze-worldstate/tests/test_extraction.py` covering: relevance-gated no-op on ordinary content (SC-005), suspected-state + low-confidence + correct-provenance creation across all four provenances — `conversation`/`email`/`calendar`/`ingestion` (SC-001/SC-002, FR-008), and duplicate-candidate attach-not-duplicate via `matching.py` (FR-010)
- [ ] T026 [P] [US1] Write `core/ze-worldstate/tests/test_matching.py` covering entity-overlap match, embedding-tiebreaker fallback, and dismissed-evidence-recognition (FR-011) paths
- [ ] T027 [US1] Write an `apps/ze-api/tests/` integration-style test exercising `GET /api/v0/loops` and `GET /api/v0/loops/{id}` end-to-end against a suspected loop created via the extraction path (mocked stores/LLM/embedder per `docs/testing.md`)

**Checkpoint**: An inferred loop can be captured as a suspicion with honest provenance/evidence from any of the four required inflows, and read back via the API — User Story 1 is independently functional and testable.

---

## Phase 4: User Story 2 - User-declared loop trusted immediately (Priority: P1)

**Goal**: When the user explicitly states unfinished business, the loop is created directly in `active` state with provenance `user_declared` and full confidence — no confirmation step.

**Independent Test**: Have the user state a task explicitly; verify a loop is created in `active` state with provenance `user_declared` and no pending confirmation, and that saying it's done closes it.

### Implementation for User Story 2

- [ ] T028 [US2] Extend `core/ze-worldstate/ze_worldstate/extraction.py`'s `propose_loop_candidates` (or add a sibling entry point) to detect `provenance = "user_declared"` inputs and create the resulting `OpenLoop` directly in `active` state at high confidence, bypassing `matching.py`'s suspicion-dedup path but still linking entity/evidence (FR-006, data-model.md validation rule: `user_declared` ⇒ `active` + high confidence, no confirmation)
- [ ] T029 [US2] Wire a `user_declared` detection/classification step into the same conversation-turn processing call site from T021, so an explicit statement like "remind me I need to follow up with the accountant" routes through the `active`-direct-entry path instead of the `suspected` path
- [ ] T030 [US2] Wire "it's done" recognition into the same conversation processing call site so it resolves the matching loop (via `matching.py`'s entity/title resolution) and invokes `PostgresLoopStore.transition(..., "closed")` — the `active → closed` transition itself is already implemented and tested in T010/T012; this task is only the recognition + call-site wiring
- [ ] T031 [P] [US2] Write `core/ze-worldstate/tests/test_extraction.py` additions (or a dedicated test) covering: `user_declared` → `active` + high confidence + no confirmation (SC-002), and the declared-loop → `closed` transition on user follow-up

**Checkpoint**: Declared loops bypass the suspicion step entirely and can be closed by the user — User Story 2 is independently functional, and coexists with User Story 1's inferred path.

---

## Phase 5: User Story 3 - Loops connect to the rest of the world (Priority: P2)

**Goal**: A loop about a known subject resolves to the existing memory-graph entity (not a duplicate) and is reachable when traversing that entity's neighbourhood.

**Independent Test**: Create a loop mentioning a known entity; verify it links to the existing entity and is reachable from that entity's neighbourhood traversal.

### Implementation for User Story 3

- [ ] T032 [P] [US3] Add a generic `"open_loop"` bucket to `_TYPE_BUCKET` in `core/ze-memory/ze_memory/graph/store.py`'s `expand()` (additive, one-line pattern matching the existing `"signal"` bucket, per research.md §2 — no domain knowledge added to `ze-memory`)
- [ ] T033 [P] [US3] Add the matching field to `GraphExpansion` in `core/ze-memory/ze_memory/graph/types.py` so expanded neighbourhoods carry `open_loop` entries
- [ ] T034 [US3] Ensure `PostgresLoopStore.link_entity` (T010) and `extraction.py`'s entity-resolution call (T014) always resolve against `ze-memory`'s existing entity resolver before creating a link, so a loop about "Maria" attaches to the existing `memory_entities` row rather than creating a new one (FR-012, SC-004's ≥95% bar)
- [ ] T035 [P] [US3] Write a `core/ze-memory/tests/` test (or extend an existing `graph/store`/`graph/types` test) verifying `GraphStore.expand()` surfaces an `"open_loop"`-typed relationship in the returned `GraphExpansion`
- [ ] T036 [US3] Write a `core/ze-worldstate/tests/` integration-style test: create a contact entity, create a loop mentioning it via `extraction.py`, then call `GraphStore.expand()` on that entity and assert the loop is present in the neighbourhood (SC-004's independent test)
- [ ] T037 [US3] Extend `get_loop` (`rest.py`, T018) to additionally resolve and include `entities` (canonical name + type) in `LoopDetail`, matching contracts/loops-api.md's response shape; extend the `apps/ze-api/tests/` integration test from T027 to assert entity linkage appears in `GET /api/v0/loops/{id}`

**Checkpoint**: Loops are provably part of the entity graph, not a silo — User Story 3 is independently testable via graph traversal.

---

## Phase 6: User Story 4 - User reviews and manages open loops (Priority: P2)

**Goal**: The user can list loops (distinguishing suspected from confirmed), and transition any loop through confirm/close/drop, with changes persisting.

**Independent Test**: With a mix of `suspected`/`active` loops, exercise list + confirm/close/drop and verify persistence on next read.

### Implementation for User Story 4

- [ ] T038 [US4] Implement `core/ze-worldstate/ze_worldstate/review.py`: `confirm_loop`, `close_loop`, `drop_loop` functions wrapping `LoopStore.transition`, mirroring `ze_personal/contacts`' propose→review shape (FR-007) — `confirm` only valid from `suspected`, `close` valid from `active`/`drifting`, `drop` valid from any non-terminal state and additionally computes/stores `dismissed_evidence_fingerprint` (data-model.md) so FR-011's re-implication check has something to match against
- [ ] T039 [US4] Add `POST /api/v0/loops/{loop_id}/confirm`, `/close`, `/drop` routes to `apps/ze-api/ze_api/api/routes/loops.py` per contracts/loops-api.md (`operation_id`s `confirmLoop`/`closeLoop`/`dropLoop`, `LoopTransitionResponse` schema in `schemas.py`, 409 on `InvalidLoopTransitionError`, 404 on `LoopNotFoundError`)
- [ ] T040 [US4] Wire the three transition routes to `review.py`'s functions via `rest.py` plain-dict wrappers (`confirm_loop`/`close_loop`/`drop_loop`), following the same `rest.py` pattern as `list_loops`/`get_loop` (T018)
- [ ] T041 [P] [US4] Write `core/ze-worldstate/tests/test_review.py` covering all valid transitions, the invalid-transition error path, that `drop` persists a `dismissed_evidence_fingerprint`, **and that `close`/`drop` never delete the loop's linked `memory_entities`/`memory_facts`/`memory_episodes` rows or the referenced entities themselves (FR-013) — only `open_loops.state` and the loop's own `memory_relationships` rows change**
- [ ] T042 [US4] Extend the `apps/ze-api/tests/` integration test (T027) to cover `confirm`/`close`/`drop` end-to-end, asserting state persists across a subsequent `GET /api/v0/loops`
- [ ] T043 [P] [US4] Create `apps/ze-web/src/entities/loop/api/useLoopsQuery.ts`, `useLoopTransitionMutation.ts`, and `apps/ze-web/src/entities/loop/index.ts` per FSD conventions (query hook in entities, mutation in entities since it's loop-bound), using generated `@ze/client` SDK types
- [ ] T044 [US4] Create `apps/ze-web/src/widgets/loop-review/LoopReviewList.tsx` — minimal list + confirm/close/drop actions, visibly distinguishing `suspected` from `active`/other rows, mirroring the existing contacts review widget (`apps/ze-web/src/widgets/contacts-overview`) shape
- [ ] T045 [P] [US4] Write a vitest test for `LoopReviewList` covering the suspected-vs-active visual distinction and that a transition action calls the mutation hook

**Checkpoint**: Full lifecycle management is usable end-to-end via API and web UI — User Story 4 is independently functional.

---

## Phase 7: Cross-cutting — confidence decay cascade (FR-004, SC-006)

**Purpose**: Wire the synchronous confidence-decay cascade so a loop's confidence measurably drops when its cited evidence is contradicted/expired/retracted. This spans US1 (evidence links must already exist) and is independent of US2–US4, so it is broken out as its own phase per research.md §3–§4 rather than force-fit into a single user story.

- [ ] T046 [P] Implement `cascade_from_evidence(evidence_type, evidence_id, loop_store)` in `core/ze-worldstate/ze_worldstate/decay.py` per contracts/loops-api.md's signature — looks up loops linked via `memory_relationships` (`source_type="open_loop"`, matching `target_type`/`target_id`), and applies multiplicative/weighted-average decay (floor `0.05`, never exactly `0.0`) per research.md §4
- [ ] T047 Call `ze_worldstate.decay.cascade_from_evidence` from the existing memory contradiction/expiry call sites already invoked from `ze-api` (`ze_memory`'s write-time NLI contradiction hook and episode-expiry-in-consolidation paths) — the shared caller that already touches both `LoopStore` and the memory store, per research.md §3 (never adding a `ze-worldstate` dependency to `ze-memory` itself)
- [ ] T048 [P] Write `core/ze-worldstate/tests/test_decay.py` covering: single-evidence loop confidence collapses toward the floor on retraction, multi-evidence loop recomputes from remaining evidence, and floor is never exactly `0.0` (SC-006)
- [ ] T049 Extend the `apps/ze-api/tests/` integration test to contradict/expire a fact a loop cites and assert the loop's confidence measurably drops on the next `GET /api/v0/loops/{id}` (quickstart.md's "Evidence retraction cascade" scenario)

**Checkpoint**: Evidence-linked belief works — confidence is not static once evidence is undermined.

---

## Phase 8: Cross-cutting — stale-suspicion expiry job (Assumptions, Clarification #5)

**Purpose**: `suspected` loops that are never confirmed or dismissed expire automatically (~14 days) via a scheduled `ze-proactive` job, so they do not accumulate forever (Edge Cases).

- [ ] T050 [P] Implement `core/ze-worldstate/ze_worldstate/jobs/stale_suspicion.py` — a `ProactiveJob`-conforming class (mirrors `plugins/ze-calendar/ze_calendar/jobs/calendar_reminder.py`'s shape) that sweeps `suspected` loops older than a configured window (default 14 days) and transitions them to `dropped` via `LoopStore.transition` (never deletes)
- [ ] T051 Register the job in `apps/ze-api/ze_api/compose.py`'s `register_all_proactive_jobs`, following the same call shape as `register_automation_jobs`/`register_correlation_jobs`, wired against the `worldstate` stack's `loop_store`
- [ ] T052 [P] Write `core/ze-worldstate/tests/jobs/test_stale_suspicion.py` covering: a `suspected` loop older than the window is transitioned to `dropped`; a `suspected` loop within the window and any non-`suspected` loop are left untouched

**Checkpoint**: Stale suspicions self-clean without manual intervention.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Final checks spanning all user stories.

- [ ] T053 [P] Add `ze-worldstate` to `docs/testing.md`'s package test table (`make test-worldstate` or equivalent) and confirm `make test-all` picks it up
- [ ] T054 [P] Add `ze_worldstate` module paths / data-domain export hook wiring so `ze-data`'s `DataPortabilityService` includes `open_loops` in export/delete, matching plan.md's `ze-data` dependency (`DataDomain` export/delete) — add a `worldstate_data_domains(pool)` export in `bootstrap.py` and wire it into `container.py`'s data-domain aggregation alongside `automation_data_domains`
- [ ] T055 Run the full `quickstart.md` walkthrough (scenarios 1–5) against a local `make dev` + `make db-up` stack and confirm each Expected outcome, including the two edge cases (duplicate capture, dismissed-then-re-implied) not otherwise covered by a unit test
- [ ] T056 Update `specs/phases/109-open-loop-substrate/spec.md`'s `**Status**` field from `Draft` to `Implemented` (or the repo's equivalent terminal status) in the same commit that completes T055, per this repo's Spec Status Audit convention
- [ ] T057 [P] Update root `CLAUDE.md`'s package dependency graph, repository layout tree, and Phase status table to add `ze-worldstate` and mark Phase 109 `Done`, matching how prior phases (e.g. 108) were recorded

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (T005–T013 establish types/errors/migration/store that every story's code imports).
- **User Story 1 (Phase 3)**: Depends on Foundational. This is the MVP — no dependency on US2–US4. Now includes wiring all four FR-008 inflows (conversation T021, email/messenger T022, calendar T023, ingestion T024).
- **User Story 2 (Phase 4)**: Depends on Foundational; reuses `extraction.py`/`propose_loop_candidates` scaffolding from US1 (T014) but adds its own direct-entry branch — implement after US1 for a clean diff, though the `active`-direct-entry logic (T028) does not require US1's `suspected` path to be feature-complete first.
- **User Story 3 (Phase 5)**: Depends on Foundational + US1's entity-resolution call in `extraction.py` (T014) existing to attach to; independently testable via graph traversal once T032–T034 land. T037 extends `get_loop` (originally scoped to evidence-only in T018) to add entity data — the entity-inclusion work lives entirely in US3, not duplicated in US1.
- **User Story 4 (Phase 6)**: Depends on Foundational (`LoopStore.transition`, T010) only — does not require US1/US2/US3 to be complete, though it is most demoable once loops exist to review (US1 or US2 done first in practice).
- **Decay cascade (Phase 7)**: Depends on Foundational + US1's evidence-linking (T016) existing.
- **Stale-suspicion job (Phase 8)**: Depends on Foundational (`LoopStore.transition`) only.
- **Polish (Phase 9)**: Depends on all desired stories/phases being complete.

### User Story Dependencies

- **US1 (P1)**: Foundational only. No dependency on other stories. MVP. Covers all four FR-008 inflows.
- **US2 (P1)**: Foundational only; shares `extraction.py` file with US1 (sequence to avoid merge conflicts, not a functional dependency).
- **US3 (P2)**: Foundational + reads on US1's entity-resolution call site; owns all `LoopDetail.entities` work (not duplicated in US1's `get_loop` task).
- **US4 (P2)**: Foundational only.

### Parallel Opportunities

- T005/T006 (types/errors) in parallel; T011/T012 in parallel once T010 lands.
- Within US1: T014 and T025/T026 test-writing can proceed once the functions they test have a stub signature; T017's route file and T019's bootstrap file are different files and can be built in parallel with T014–T016 once T009/T010 exist. T022/T023/T024 (the three additional inflow wirings) touch different call sites (`ze-messenger`, `ze-calendar`, ingestion pipeline) and can be staffed in parallel once T021 establishes the pattern.
- US3's graph-substrate tasks (T032, T033) touch only `ze-memory` and are fully parallel with US1/US2 work in `ze-worldstate`.
- US4's web tasks (T043–T045) are parallel with any backend work once the REST contract (T039/T040) is stable.
- Phase 7 (decay) and Phase 8 (stale-suspicion job) are mutually independent and can be staffed in parallel once Foundational + US1 evidence-linking exist.

---

## Parallel Example: User Story 1

```bash
# Once Foundational (T005-T013) is done, launch together:
Task: "Implement extraction relevance gate in core/ze-worldstate/ze_worldstate/extraction.py"
Task: "Implement entity-overlap/embedding matching in core/ze-worldstate/ze_worldstate/matching.py"

# Once T014/T015 land, launch together:
Task: "Add GET /api/v0/loops + /{id} routes and schemas"
Task: "Implement build_worldstate_stack in bootstrap.py"
Task: "Write test_extraction.py and test_matching.py"

# Once T021 (conversation wiring) establishes the pattern, launch together:
Task: "Wire propose_loop_candidates into ze-messenger inbound processing (email)"
Task: "Wire propose_loop_candidates into ze-calendar sync"
Task: "Wire propose_loop_candidates into the ingestion pipeline"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything)
3. Complete Phase 3: User Story 1 — inferred loops captured as suspicions from all four required inflows, readable via API
4. **STOP and VALIDATE**: run quickstart.md scenario 1 against a live `make dev` stack
5. This alone makes SC-001/SC-002 (partially, for the inferred half), FR-008 (all four inflows), and SC-005 demonstrable

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → validate → demo (MVP: the "active concerns" face is no longer empty, all four inflows wired)
3. US2 → validate → demo (both admission paths distinguished)
4. US4 → validate → demo (lifecycle management usable, even before graph linkage)
5. US3 → validate → demo (doctrinally correct: projection of world-state, not a silo)
6. Decay cascade (Phase 7) + stale-suspicion job (Phase 8) → validate → demo (SC-006, Edge Cases fully covered)
7. Polish (Phase 9) → spec status flip, docs updates

### Suggested Team Split

- Developer A: Foundational → US1 → decay cascade (owns `ze_worldstate/{types,store,extraction,matching,decay}.py`)
- Developer B: US4 review/REST/web (owns `review.py`, routes, `apps/ze-web`)
- Developer C: US3 graph-substrate addition (owns `ze-memory` changes) + stale-suspicion job + the three additional US1 inflow wirings (T022–T024), since those touch `ze-messenger`/`ze-calendar`/ingestion call sites rather than `ze-worldstate` internals

---

## Notes

- [P] tasks = different files, no dependencies within their phase.
- [Story] label maps task to specific user story for traceability; Phases 7–8 are cross-cutting and intentionally unlabeled since they serve FR-004 and the Assumptions section rather than a single user story.
- This feature explicitly does NOT touch the goal engine/schema (FR-016) — no task here modifies `core/ze-automation/ze_automation/goals/*`.
- FR-017's proto-contribution is satisfied by direct function calls (T021–T024, T030, T047) from existing write paths — no new seam/event-bus is built (Out of Scope, Phase B).
- FR-008 requires all four inflows (conversation, email/messenger, calendar, ingestion); T021–T024 wire each one explicitly rather than leaving three of them implicit.
- `LoopDetail`'s two payload additions (evidence, entities) are deliberately split across stories: evidence in T018 (US1, needed for the "why does Ze think this?" MVP surface), entities in T037 (US3, since entity resolution is that story's concern) — avoid re-adding entity lookups to T018.
- Verify tests fail before implementing where a test task precedes its implementation task in the same story; several tasks above co-locate implementation and its test in one task for tightly-coupled single-file modules (matches this repo's existing test-alongside-code convention).
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
