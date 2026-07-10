---

description: "Task list for Model Default with Overrides (specs/phases/103-model-default-overrides)"
---

# Tasks: Model Default with Overrides

**Input**: Design documents from `/specs/phases/103-model-default-overrides/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Included — constitution Principle V ("Test Discipline (NON-NEGOTIABLE)") requires every feature to ship with tests; no real DB/LLM in unit tests.

**Organization**: Tasks are grouped by user story (spec.md: US1 = Trial a new model everywhere, P1; US2 = Pin a specific agent, P2; US3 = Capability-specific steps stay pinned, P2) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact, relative to repo root

## Path Conventions

Existing Ze monorepo layout (see `plan.md` Project Structure): `core/ze-agents/`,
`core/ze-core/`, `plugins/ze-personal/`, `plugins/ze-calendar/`, `apps/ze-api/`. No
new package.

---

## Phase 1: Setup

**Purpose**: Confirm the call-site inventory from research.md still matches the
working tree before any code changes (no new package, no new dependencies needed).

- [X] T001 Re-run the call-site grep from research.md §2 (`resolve_model`,
      `models.get(`, `agent_cls.model`) across `core/ze-core/`, `plugins/ze-personal/`,
      `plugins/ze-calendar/`, `apps/ze-api/` to confirm no drift since planning; note
      any new/removed call sites before proceeding

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared resolver and startup validation that every user story
depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 Create `core/ze-agents/ze_agents/model_resolution.py` with
      `resolve_model(key: str, declared: str | None, config: dict) -> str`
      (override → declared → default, raising `AgentConfigError` from
      `ze_agents.errors` if no default is configured) and
      `KNOWN_STEP_KEYS: frozenset[str]` = `{"router_fallback", "synthesis",
      "session_title", "workflow_verify", "insights", "reminders"}`, and
      `validate_model_config(config: dict, known_keys: frozenset[str]) -> None`
      (raises `AgentConfigError` if `models.default` is missing/empty, or if any
      `models.overrides` key is not in `known_keys`)
- [X] T003 [P] Write `core/ze-agents/tests/test_model_resolution.py` covering:
      override wins over declared and default; declared wins over default when no
      override; default used when neither override nor declared is set;
      `AgentConfigError` when `models.default` missing/empty; `AgentConfigError`
      when an `overrides` key is not in `known_keys` (depends on T002)
- [X] T004 Wire `validate_model_config()` into
      `core/ze-core/ze_core/container.py` startup, called once alongside the
      existing `RouterConfig` construction with `known_keys` = the union of
      `get_enabled_agents().keys()` and `model_resolution.KNOWN_STEP_KEYS`
      (depends on T002)
- [X] T005 [P] Add startup-validation tests to `core/ze-core/tests/test_container.py`
      for T004: missing `models.default` raises at startup; an unknown
      `models.overrides` key (both an agent-name-shaped typo and a step-key-shaped
      typo) raises at startup (depends on T004)
- [X] T006 Restructure `apps/ze-api/config/config.yaml`: add `models.default:
      tencent/hy3:free` and `models.overrides: {}`; remove the dead
      `routing.synthesis`, `routing.profile`, `routing.reminders`,
      `routing.insights`, `routing.whisper`, `routing.vision_caption`,
      `routing.workflow_verify` keys and the unused `models.router` key (per
      research.md §2 — none of these are actually read by any call site today);
      keep `routing.gap_threshold` unchanged; keep `models.embedding`,
      add/keep `models.whisper`, `models.vision_caption` as the capability-pinned
      keys (depends on T002, T004 — config must satisfy validation before `make dev`
      can boot)

**Checkpoint**: Foundation ready — `make dev` boots successfully with the new config
shape and fails loudly on a misconfigured one; user story implementation can now
begin.

---

## Phase 3: User Story 1 - Trial a new model across the whole assistant with one edit (Priority: P1) 🎯 MVP

**Goal**: Every general-purpose agent and routing/support step that has no
override picks up `models.default` on its next request, with no restart and no
per-file edits.

**Independent Test**: Change only `models.default` in `config.yaml`, send a
message to a non-overridden agent without restarting the backend, and confirm via
the message trace that the new model was used (quickstart.md Scenario 1).

### Implementation for User Story 1

- [X] T007 [US1] Add a `config: dict` constructor param to `EmbeddingRouter` in
      `core/ze-core/ze_core/routing/router.py` and rewrite `_resolve_model()` to
      compute the same `declared` value as today (agent's `model_simple` on
      `complexity == "simple"`, else `model`) and pass it through
      `ze_agents.model_resolution.resolve_model(agent_name, declared, self._config)`
      (depends on T002)
- [X] T008 [US1] Pass `settings.config` into the `EmbeddingRouter(...)`
      construction in `core/ze-core/ze_core/container.py` (same block that builds
      `RouterConfig`) (depends on T007)
- [X] T009 [P] [US1] Wire `synthesize()` in
      `core/ze-core/ze_core/orchestration/nodes/memory.py` to call
      `resolve_model("synthesis", MODEL_SYNTHESIS, cfg)` from
      `ze_agents.model_resolution`/`ze_agents.defaults` instead of the inline
      `models.get("synthesis", ...)` lookup (depends on T002)
- [X] T010 [P] [US1] Wire the router LLM-decomposition fallback in
      `core/ze-core/ze_core/container.py` (`RouterConfig(fallback_model=...)`
      construction) to call `resolve_model("router_fallback",
      MODEL_ROUTER_FALLBACK, settings.config)` instead of
      `routing_cfg.get("fallback_model", ...)` (depends on T002)
- [X] T011 [P] [US1] Wire `apps/ze-api/ze_api/api/websocket/session_titles.py` to
      call `resolve_model("session_title", _DEFAULT_MODEL, config)` instead of the
      inline `config.get("models", {}).get("session_title", ...)` lookup (depends
      on T002)
- [X] T012 [P] [US1] Wire `_resolve_verify_model()` in
      `plugins/ze-personal/ze_personal/graph/workflow.py` to call
      `resolve_model("workflow_verify", MODEL_WORKFLOW_VERIFY, cfg)` (depends on
      T002)
- [X] T013 [P] [US1] Wire the model lookup in
      `plugins/ze-personal/ze_personal/jobs/insights.py::run()` to call
      `resolve_model("insights", "anthropic/claude-haiku-4-5",
      self._settings.config)` (depends on T002)
- [X] T014 [P] [US1] Wire the model lookup in
      `plugins/ze-calendar/ze_calendar/reminders/calendar.py::_assess_intervals()`
      to call `resolve_model("reminders", "anthropic/claude-haiku-4-5",
      self._settings.config)` (depends on T002)
- [X] T015 [US1] Update existing unit tests to assert the new resolution path at
      each wired call site: `core/ze-core/tests/routing/test_router.py`,
      `core/ze-core/tests/orchestration/nodes/test_memory.py`,
      `core/ze-core/tests/test_container.py`,
      `apps/ze-api/tests/api/test_sessions_route.py` (or the websocket
      session-title test, if separate), `plugins/ze-personal/tests/graph/test_workflow.py`,
      `plugins/ze-personal/tests/jobs/test_insights.py`,
      `plugins/ze-calendar/tests/jobs/test_reminders.py` — each should assert that
      changing `models.default` in the mocked config changes the resolved model at
      that call site (depends on T007–T014)
- [ ] T016 [US1] Run quickstart.md Scenarios 1, 6, and 7 manually against `make dev`
      to confirm default propagation without restart, the shipped
      `tencent/hy3:free` trial default, and a one-line revert (depends on T015)
      **DEFERRED**: no `.env` present in this checkout, so `make dev` cannot boot in
      this environment (needs `OPENROUTER_API_KEY` etc.) — left for the maintainer to
      run manually.

**Checkpoint**: User Story 1 is fully functional — a maintainer can swap
`models.default` and see it take effect everywhere with zero code changes.

---

## Phase 4: User Story 2 - Pin a specific agent to a specific model (Priority: P2)

**Goal**: A named agent or step can be pinned to a specific model via
`models.overrides`, independent of `models.default`, and a typo in an override key
is caught at startup rather than silently ignored.

**Independent Test**: Set `models.overrides` for one agent while `models.default`
points elsewhere; confirm only that agent uses the override (quickstart.md
Scenario 2). Add a typo'd override key and confirm startup fails
(quickstart.md Scenario 5).

### Implementation for User Story 2

- [X] T017 [US2] Add a test to `core/ze-core/tests/routing/test_router.py` (or
      `test_router_integration.py`) proving an entry in `models.overrides` pins one
      agent's resolved model while a sibling agent with no override follows
      `models.default` (depends on T007, T015)
- [X] T018 [US2] Extend `core/ze-agents/tests/test_model_resolution.py` with a case
      proving that removing an override entry and re-resolving falls back to the
      declared model (or default, if no declared model) — exercises the "live
      re-read" behavior from research.md §1 (depends on T003)
- [X] T019 [US2] Extend the startup-validation tests in
      `core/ze-core/tests/test_container.py` (from T005) with an explicit
      "unknown override key" case using an agent-name-shaped typo, confirming the
      error message names the offending key (depends on T004, T005)
- [ ] T020 [US2] Run quickstart.md Scenarios 2 and 5 manually to confirm override
      precedence and fail-fast on a typo'd override key (depends on T017–T019)
      **DEFERRED**: same `.env`/live-server constraint as T016 — left for the
      maintainer to run manually.
- [X] T021 [US2] Update `docs/configuration.md` to document `models.default` and
      `models.overrides`: the override → declared → default resolution order, how
      to add/remove an override, the startup fail-fast behavior for a missing
      default or unknown key, and the known limitation (from data-model.md) that
      the `reminders` key is shared between the reminders agent and the reminder
      interval assessor (depends on T017–T019)

**Checkpoint**: User Stories 1 AND 2 both work independently — the default is safe
to change fleet-wide, and any agent that needs to stay pinned can be.

---

## Phase 5: User Story 3 - Capability-specific steps are never silently swapped (Priority: P2)

**Goal**: Changing `models.default` never affects audio transcription, vision
captioning, or embedding — they keep using their own pinned `models.whisper`,
`models.vision_caption`, `models.embedding` values.

**Independent Test**: Change `models.default`, send a voice message and an image
message, and confirm (via trace/logs) that transcription and captioning still use
their previously configured models (quickstart.md Scenario 3).

### Implementation for User Story 3

- [X] T022 [P] [US3] Create `core/ze-core/tests/orchestration/nodes/test_preprocessing.py`
      asserting that `preprocess()` in
      `core/ze-core/ze_core/orchestration/nodes/preprocessing.py` resolves the
      transcription model from `models.whisper` and the vision-caption model from
      `models.vision_caption` regardless of what `models.default` is set to (no
      production code change expected here — this call site intentionally bypasses
      `resolve_model`; the test documents and locks in that exclusion) (depends on
      T006)
- [X] T023 [P] [US3] Add a test near the embedding-model wiring in
      `core/ze-core/ze_core/container.py` (e.g. `core/ze-core/tests/test_container.py`)
      asserting `models.embedding` resolution is unaffected by `models.default`
      changes (depends on T006)
- [ ] T024 [US3] Run quickstart.md Scenario 3 manually (send a voice message and an
      image message after changing `models.default`) to confirm no regression
      (depends on T022, T023)
      **DEFERRED**: same `.env`/live-server constraint as T016 — left for the
      maintainer to run manually.

**Checkpoint**: All three user stories are independently functional — the default
is safe to change without breaking capability-specific steps.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Definition-of-done items spanning all stories (constitution
"Development Workflow": spec status updated, tests green, lint clean,
`specs/README.md` index row updated).

- [X] T025 Update the `Status` field in
      `specs/phases/103-model-default-overrides/spec.md` from `Draft` to
      `Implemented` and add the phase 103 row to `specs/README.md`'s index
      (depends on T016, T020, T024)
- [X] T026 [P] Run `make lint` and `make format` across touched packages
      (`ze-agents`, `ze-core`, `ze-personal`, `ze-calendar`, `ze-api`)
- [X] T027 Run `make test-agents`, `make test-core`, `make test-personal`,
      `make test-calendar`, `make test` (ze-api) to confirm all touched suites are
      green (depends on T026)
- [ ] T028 Run the full quickstart.md validation end-to-end (all 7 scenarios) as
      final sign-off (depends on T027)
      **DEFERRED**: same `.env`/live-server constraint as T016 — left for the
      maintainer to run manually before merging.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — delivers the MVP alone
- **User Story 2 (Phase 4)**: Depends on Foundational; its tests build on US1's
  wiring (T007, T015) but add no new production wiring of its own — the override
  mechanism already exists in T002/T004
- **User Story 3 (Phase 5)**: Depends on Foundational (specifically T006's
  config.yaml restructure); purely additive test coverage, no production code
  changes
- **Polish (Phase 6)**: Depends on all three user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: No dependencies on US2/US3 — independently shippable MVP
- **User Story 2 (P2)**: Technically reuses US1's wiring to write its tests (same
  `resolve_model` call sites already read `models.overrides`), but delivers
  distinct, independently verifiable value (per-agent pinning + fail-fast
  validation)
- **User Story 3 (P2)**: Independent of US1/US2 — verifies something that doesn't
  change; can be done in parallel with US2

### Parallel Opportunities

- T009, T010, T011, T012, T013, T014 (US1 call-site wiring) can all run in
  parallel once T002 is done — each touches a different file
- T022 and T023 (US3) can run in parallel with each other and with US2's tasks
- T003 and T005 can run in parallel with each other (different files) once their
  respective dependencies (T002, T004) land

---

## Parallel Example: User Story 1

```bash
# Once T002 (resolver) and T007/T008 (router wiring + config wiring) are done,
# launch all remaining call-site wiring tasks together:
Task: "Wire synthesize() in core/ze-core/ze_core/orchestration/nodes/memory.py"
Task: "Wire RouterConfig.fallback_model in core/ze-core/ze_core/container.py"
Task: "Wire apps/ze-api/ze_api/api/websocket/session_titles.py"
Task: "Wire _resolve_verify_model() in plugins/ze-personal/ze_personal/graph/workflow.py"
Task: "Wire jobs/insights.py in plugins/ze-personal"
Task: "Wire reminders/calendar.py in plugins/ze-calendar"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (resolver + startup validation + config.yaml
   restructure — CRITICAL, blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md Scenarios 1, 6, 7
5. At this point `models.default: tencent/hy3:free` is live everywhere and
   revertible in one edit — the core friction from the original request is solved

### Incremental Delivery

1. Setup + Foundational → boots with new config shape, fails loudly on
   misconfiguration
2. User Story 1 → global default trial works end-to-end (MVP)
3. User Story 2 → per-agent pinning + fail-fast on override typos
4. User Story 3 → locked-in regression coverage for capability-specific models
5. Polish → docs, lint, full test suite, spec status flip

---

## Notes

- [P] tasks touch different files with no unmet dependency
- [Story] labels map every implementation/test task to its user story for
  traceability
- No `contracts/` directory exists for this feature (no external interface) — see
  plan.md
- Commit after each task or logical group; do not batch unrelated call-site wirings
  into one commit if avoidable, since each is independently revertible
