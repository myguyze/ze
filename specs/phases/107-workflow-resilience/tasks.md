---

description: "Task list for Workflow Resilience and Control (107)"
---

# Tasks: Workflow Resilience and Control

**Input**: Design documents from `/specs/phases/107-workflow-resilience/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — constitution Principle V (Test Discipline) is non-negotiable; graph, store, scheduler, REST, and agent-tool paths ship tests.

**Organization**: Tasks grouped by user story (spec.md priorities P1–P6) for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US6 map to spec.md user stories

## Path Conventions

Existing monorepo (see plan.md): `core/ze-automation/`, `plugins/ze-personal/`, `apps/ze-api/`, `apps/ze-web/`.

---

## Phase 1: Setup

**Purpose**: Confirm scaffolding; no new packages, migrations, or dependencies (plan.md — JSONB field extensions only).

- [x] T001 Confirm `workflows.steps` and `workflow_executions.step_results` JSONB columns in `core/ze-automation/ze_automation/migrations/` need no new migration for `on_failure`, `attempt_count`, and `no_results` (data-model.md)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types, validation, and store serialization every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Add `on_failure: str = "fail"` to `WorkflowStep` in `core/ze-automation/ze_automation/workflow/types.py`
- [x] T003 [P] Add `attempt_count: int = 1` and `no_results: bool = False` to `StepResult` in `core/ze-automation/ze_automation/workflow/types.py`
- [x] T004 Create `validate_workflow_steps()` in `core/ze-automation/ze_automation/workflow/validation.py` (duplicate ids, dangling branch/default_next/`skip_to` targets per data-model.md)
- [x] T005 Extend `validate_step_targets()` in `core/ze-automation/ze_automation/workflow/planner.py` to validate `on_failure: skip_to:<step_id>` targets via `validate_workflow_steps()` — depends on T004
- [x] T006 Extend `_step_to_dict` / `_step_from_dict` for `on_failure` (default `"fail"` when absent) in `core/ze-automation/ze_automation/workflow/postgres.py` — depends on T002
- [x] T007 [P] Extend `_step_result_to_dict` / `_step_result_from_dict` for `attempt_count` and `no_results` in `core/ze-automation/ze_automation/workflow/postgres.py` — depends on T003
- [x] T008 Add `update_steps(workflow_id, steps)` to `WorkflowStore` protocol in `core/ze-automation/ze_automation/workflow/store.py` — depends on T002
- [x] T009 Implement `update_steps()` in `PostgresWorkflowStore` (`core/ze-automation/ze_automation/workflow/postgres.py`) calling `validate_workflow_steps()` before UPDATE — depends on T004, T006, T008
- [x] T010 [P] Unit tests for `validate_workflow_steps()` in `core/ze-automation/tests/workflow/test_validation.py` — depends on T004
- [x] T011 [P] Unit tests for JSONB round-trip of new step/step-result fields in `core/ze-automation/tests/workflow/test_postgres.py` — depends on T006, T007

**Checkpoint**: Foundation ready — types, validation, and `update_steps` exist and are tested.

---

## Phase 3: User Story 1 — Resilient steps don't kill the whole run (Priority: P1) 🎯 MVP

**Goal**: Per-step `on_failure` policy (`fail` | `continue` | `skip_to:<step_id>`) keeps runs alive when non-fail steps fail; mixed/all-fail completion rules (FR-009a/b).

**Independent Test**: Workflow with step 1 `on_failure: continue` that fails verification still reaches step 2 and completes; step 1 failure visible in history (quickstart.md Story 1).

### Tests for User Story 1

- [x] T012 [P] [US1] Graph tests for `continue`, `skip_to`, and default `fail` policies in `plugins/ze-personal/tests/graph/test_workflow.py`
- [x] T013 [P] [US1] Graph test: all steps `on_failure: continue`, all fail → run status `failed` (FR-009b) in `plugins/ze-personal/tests/graph/test_workflow.py`

### Implementation for User Story 1

- [x] T014 [US1] Implement `handle_step_failure` node in `plugins/ze-personal/ze_personal/graph/workflow.py` (apply `on_failure`: fail→FAIL, continue→next list step or END, skip_to→target)
- [x] T015 [US1] Change `after_verify_step` to route step failures to `handle_step_failure` instead of `workflow_failed` in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T014
- [x] T016 [US1] Register `handle_step_failure` node and conditional edges in `build_workflow_graph()` in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T014, T015
- [x] T017 [US1] Update `workflow_synthesize` for FR-009a/b (≥1 success → `completed`; zero successes → `failed` with all-failure summary) in `plugins/ze-personal/ze_personal/graph/workflow.py`
- [x] T018 [P] [US1] Add `on_failure` to `WorkflowStepResponse` in `apps/ze-api/ze_api/api/schemas.py` — depends on T002

**Checkpoint**: User Story 1 fully functional — non-fail step failures no longer abort the whole run.

---

## Phase 4: User Story 2 — Partial results are delivered when a run does fail (Priority: P2)

**Goal**: Failed runs after partial progress include synthesized successful-step output in push alert and run-history `summary` (FR-010).

**Independent Test**: Step 1 succeeds, step 2 with `on_failure: fail` fails → notification and `summary` contain step 1 output (quickstart.md Story 2).

### Tests for User Story 2

- [x] T019 [P] [US2] Graph tests for partial synthesis in `workflow_failed` (with/without prior successes) in `plugins/ze-personal/tests/graph/test_workflow.py`

### Implementation for User Story 2

- [x] T020 [US2] Extend `workflow_failed` to LLM-synthesize successful steps into `finish_execution(..., summary=...)` when ≥1 step succeeded in `plugins/ze-personal/ze_personal/graph/workflow.py`
- [x] T021 [US2] Update `_workflow_failure_handler` to prefer `execution.summary` over `str(exc)[:200]` for notification body in `core/ze-automation/ze_automation/bootstrap.py` — depends on T020

**Checkpoint**: User Stories 1 and 2 both work — resilient routing plus partial value recovery on true failures.

---

## Phase 5: User Story 3 — Transient glitches don't fail a whole run (Priority: P3)

**Goal**: Automatic step retries (2 retries / 3 attempts, 2s delay) for transient failures before declaring step failed (FR-001–FR-003).

**Independent Test**: Simulated transient failure on first attempt succeeds on retry; `attempt_count` recorded in step result (quickstart.md Story 3).

### Tests for User Story 3

- [x] T022 [P] Unit tests for `is_transient_failure()` in `core/ze-automation/tests/workflow/test_retry.py`
- [x] T023 [P] [US3] Graph tests for retry routing and `attempt_count` in `plugins/ze-personal/tests/graph/test_workflow.py`

### Implementation for User Story 3

- [x] T024 [P] Create `retry.py` with `STEP_MAX_ATTEMPTS = 3`, `RETRY_DELAY_SECONDS = 2.0`, and `is_transient_failure()` in `core/ze-automation/ze_automation/workflow/retry.py`
- [x] T025 [US3] Add `step_attempt: int` to `WorkflowAgentState` and track/increment in `load_workflow_step` in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T024
- [x] T026 [US3] Add `retry_step` edge in `after_verify_step` and graph builder (transient + attempts remaining → reload step after delay; else → `handle_step_failure`) in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T024, T025, T015
- [x] T027 [US3] Persist `attempt_count` on `StepResult` in `_fail_step` / success paths in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T003, T025

**Checkpoint**: Transient flake recovers automatically without user intervention.

---

## Phase 6: User Story 4 — "Nothing new to report" isn't treated as a failure (Priority: P4)

**Goal**: Verify distinguishes empty findings from malfunction; planner authors monitoring-friendly criteria; `no_results` flag on step results (FR-012–FR-014).

**Independent Test**: Monitoring step with no new items → `success: true`, `no_results: true` (quickstart.md Story 4).

### Tests for User Story 4

- [x] T028 [P] [US4] Graph tests for verify `no_results` success path vs tool-error failure path in `plugins/ze-personal/tests/graph/test_workflow.py`
- [x] T029 [P] [US4] Planner tests for monitoring-shaped verify criteria in `core/ze-automation/tests/workflow/test_planner.py`

### Implementation for User Story 4

- [x] T030 [US4] Extend verify LLM JSON schema to `{"pass", "no_results", "reason"}` and record `StepResult(no_results=True)` when appropriate in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T003
- [x] T031 [US4] Update `_PLAN_SYSTEM`, `_parse_step`, and `_parse_step` output to include `on_failure` and monitoring verify guidance in `core/ze-automation/ze_automation/workflow/planner.py` — depends on T002, T005
- [x] T032 [P] [US4] Add `attempt_count` and `no_results` to `StepResultResponse` in `apps/ze-api/ze_api/api/schemas.py` — depends on T003

**Checkpoint**: Monitoring workflows no longer false-fail on empty findings.

---

## Phase 7: User Story 5 — Editing a workflow step without rebuilding (Priority: P5)

**Goal**: Edit steps via REST API and workflow agent tool; validation rejects broken graphs; schedule and history preserved (FR-015–FR-019a).

**Independent Test**: `PATCH …/steps` or chat edit changes next run's behavior; prior executions unchanged (quickstart.md Story 5).

### Tests for User Story 5

- [x] T033 [P] [US5] API tests for `PATCH /api/v0/workflows/{id}/steps` (success + 422 validation) in `apps/ze-api/tests/api/routes/test_workflows.py`
- [x] T034 [P] [US5] Agent tool tests for `edit_workflow_steps` in `core/ze-automation/tests/workflow_agent/test_tools.py`

### Implementation for User Story 5

- [x] T035 [P] [US5] Add `UpdateWorkflowStepsRequest` and `WorkflowStepInput` to `apps/ze-api/ze_api/api/schemas.py` — depends on T018
- [x] T036 [US5] Implement `update_workflow_steps()` helper in `core/ze-automation/ze_automation/rest.py` delegating to `store.update_steps()` — depends on T009
- [x] T037 [US5] Add `PATCH /api/v0/workflows/{workflow_id}/steps` route (`updateWorkflowSteps`) in `apps/ze-api/ze_api/api/routes/workflows.py` — depends on T035, T036
- [x] T038 [US5] Add `edit_workflow_steps` agent tool in `core/ze-automation/ze_automation/agents/workflow/tools.py` — depends on T009
- [x] T038b [US5] Register `edit_workflow_steps` and `cancel_workflow_run` on `WorkflowManagerAgent.tools` and document in agent instructions (`agent.py`)

**Checkpoint**: Users can tune steps (including `on_failure`) without recreating workflows.

---

## Phase 8: User Story 6 — Cancelling a run in progress (Priority: P6)

**Goal**: Cancel via REST, agent tool, and ze-web button; `cancelled` status; best-effort at step boundaries (FR-020–FR-023).

**Independent Test**: Trigger long run, cancel mid-flight → status `cancelled` within seconds; partial step results retained (quickstart.md Story 6).

### Tests for User Story 6

- [x] T039 [P] [US6] Scheduler tests for `cancel_execution()` and `is_cancelled()` in `core/ze-automation/tests/workflow_engine/test_scheduler.py`
- [x] T040 [P] [US6] Graph tests for `workflow_cancelled` node in `plugins/ze-personal/tests/graph/test_workflow.py`
- [x] T041 [P] [US6] API tests for `POST …/executions/{id}/cancel` (cancelled + not_running) in `apps/ze-api/tests/api/routes/test_workflows.py`

### Implementation for User Story 6

- [x] T042 [US6] Add `CancellationRegistry` and `cancel_execution()` / `is_cancelled()` to `WorkflowScheduler` in `core/ze-automation/ze_automation/workflow/scheduler.py` (register on trigger, clear in finally)
- [x] T043 [US6] Implement `workflow_cancelled` node and check `is_cancelled()` in `load_workflow_step` / `handle_step_failure` in `plugins/ze-personal/ze_personal/graph/workflow.py` — depends on T042; pass scheduler via `config["configurable"]` from `bootstrap.py`
- [x] T044 [US6] Wire scheduler into workflow graph config in `core/ze-automation/ze_automation/bootstrap.py` — depends on T042
- [x] T045 [P] [US6] Add `CancelWorkflowExecutionResponse` to `apps/ze-api/ze_api/api/schemas.py`
- [x] T046 [US6] Implement `cancel_workflow_execution()` in `core/ze-automation/ze_automation/rest.py` and `POST …/cancel` route in `apps/ze-api/ze_api/api/routes/workflows.py` — depends on T042, T045
- [x] T047 [US6] Add `cancel_workflow_run` agent tool in `core/ze-automation/ze_automation/agents/workflow/tools.py` — depends on T042
- [x] T047b [US6] *(merged into T038b)* Register `cancel_workflow_run` on `WorkflowManagerAgent.tools`
- [x] T048 [P] [US6] Create `useCancelExecutionMutation.ts` in `apps/ze-web/src/entities/workflow/api/` and export from `apps/ze-web/src/entities/workflow/index.ts`
- [x] T049 [US6] Add Cancel button (visible while running) and `cancelled` status styling in `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.tsx` — depends on T048
- [x] T050 [P] [US6] Display `attempt_count` and `no_results` in `apps/ze-web/src/widgets/workflow-graph/ui/StepDetailPanel.tsx` — depends on T032

**Checkpoint**: All six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: SDK codegen, regression, docs, and spec status.

- [x] T051 [P] Regenerate `@ze/client` OpenAPI types after new routes and schema fields (phase 72 codegen pattern)
- [x] T052 Run `make test-automation`, `make test-personal`, `make test-api`, and `make lint` from repo root
- [x] T053 [P] Execute quickstart.md validation scenarios and note results in PR description
- [x] T054 Update `specs/phases/107-workflow-resilience/spec.md` status field when implementation merges

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **blocks all user stories**
- **User Stories (Phases 3–8)**: All depend on Foundational completion
  - Recommended sequential order: US1 → US2 → US3 → US4 → US5 → US6 (graph file contention in `workflow.py` favors US1–US4 before US6)
  - US5 (REST edit) can parallel US3/US4 after Foundational (different files)
  - US6 scheduler work (T042) can start after Foundational; graph wiring (T043) after US1 `handle_step_failure`
- **Polish (Phase 9)**: Depends on desired user stories being complete

### User Story Dependencies

| Story | Depends on | Notes |
|-------|------------|-------|
| US1 (P1) | Foundational | MVP — no other stories required |
| US2 (P2) | US1 graph failure path | Extends `workflow_failed`; independently testable with forced `fail` step |
| US3 (P3) | US1 `handle_step_failure` routing | Retries intercept before failure handler |
| US4 (P4) | Foundational types | Mostly verify/planner; parallel with US2/US3 |
| US5 (P5) | Foundational `update_steps` | Independent of graph changes |
| US6 (P6) | US1 graph nodes | Cancellation checks reuse step-boundary hooks |

### Parallel Opportunities

- **Foundational**: T003, T007, T010, T011 in parallel after T002/T004 land
- **After Foundational**: US5 (T033–T038) in parallel with US1 (T012–T018)
- **Per story**: All tasks marked `[P]` within a phase can run concurrently
- **Graph file**: Serialize edits to `plugins/ze-personal/ze_personal/graph/workflow.py` across US1→US2→US3→US4→US6

### Parallel Example: User Story 1

```bash
# Tests first (parallel):
T012 Graph tests for continue/skip_to/fail
T013 Graph test all-fail → failed status

# Schema (parallel with graph work):
T018 WorkflowStepResponse.on_failure
```

### Parallel Example: User Story 5 (while US1–US4 in progress)

```bash
T033 API tests for PATCH steps
T034 Agent tool tests
T035 UpdateWorkflowStepsRequest schema
# then T036–T038 sequentially
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001)
2. Complete Phase 2: Foundational (T002–T011)
3. Complete Phase 3: User Story 1 (T012–T018)
4. **STOP and VALIDATE** — quickstart.md Story 1 + `make test-personal`
5. Demo/deploy if ready

### Incremental Delivery

1. Foundational → US1 (MVP: resilient routing)
2. US2 → partial synthesis on real failures
3. US3 → retry layer
4. US4 → monitoring false-failure fix
5. US5 → step editing (unblocks tuning without recreate)
6. US6 → cancellation control
7. Polish → codegen, lint, quickstart

### Parallel Team Strategy

1. Team completes Foundational together
2. Split after checkpoint:
   - **Dev A**: US1 → US2 → US3 (graph pipeline)
   - **Dev B**: US5 (REST + tools) then US6 scheduler/REST
   - **Dev C**: US4 planner/verify + web display (T050) after T032
3. Integrate graph changes sequentially; merge US5 early (low conflict)

---

## Notes

- No Alembic migration for resilience JSONB fields on `workflows.steps` — backward compatible (`on_failure` absent → `"fail"`)
- **107b** adds migration for `steps_snapshot` + `cancelled` status CHECK (see data-model.md)
- Legacy workflows MUST keep today's fail-on-first-error behavior (regression test in T012)
- Step-editing UI on ze-web is **out of scope** — cancel button only (FR-019a); snapshot display + notices **are** in scope (107b, FR-018d–g)
- `[P]` tasks = different files or read-only test authoring; graph `workflow.py` edits should not be parallelized across stories

---

## Phase 10: User Story 7 — Definition snapshots & explicit UI (Priority: P5b) *(107b follow-up)*

**Goal**: Per-run `steps_snapshot` at execution start; historical runs render snapshot; ze-web explicitly labels current vs historical definition and warns when they differ.

**Independent Test**: Edit workflow after a run → select old run → graph matches pre-edit steps + banner "definition has changed since this run" (quickstart.md Story 7).

**Prerequisites**: Phases 1–9 (107 core) complete.

### Tests for User Story 7

- [x] T055 [P] [US7] Store tests: `start_execution` persists `steps_snapshot`; `update_steps` does not mutate existing snapshots in `core/ze-automation/tests/workflow/test_postgres.py`
- [x] T056 [P] [US7] API test: `GET …/executions/{id}` includes `steps_snapshot` in `apps/ze-api/tests/api/test_workflows_route.py`
- [x] T057 [P] [US7] Web test: historical run shows edited-since banner in `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.test.tsx` (or widget-level test)

### Implementation for User Story 7

- [x] T058 [US7] Write migration `zc025_workflow_execution_snapshot_and_cancelled.py` in `core/ze-automation/ze_automation/migrations/versions/` — add `steps_snapshot JSONB`, extend status CHECK for `cancelled` *(zc025 — zc022 taken by ze-core)*
- [x] T059 [US7] Add `steps_snapshot` to `WorkflowExecution` in `core/ze-automation/ze_automation/workflow/types.py` — depends on T058
- [x] T060 [US7] Persist snapshot in `start_execution()` and serialize in `postgres.py` (`_row_to_execution`, list/get execution) — depends on T059
- [x] T061 [P] [US7] Add `steps_snapshot` to `WorkflowExecutionResponse` in `apps/ze-api/ze_api/api/schemas.py` — depends on T059
- [x] T062 [US7] Add `stepsDifferFromSnapshot(current, snapshot)` helper in `apps/ze-web/src/entities/workflow/lib/stepsSnapshot.ts` (deep compare by step ids + task + on_failure + branches)
- [x] T063 [US7] Create `WorkflowDefinitionNotice` banner component in `apps/ze-web/src/widgets/workflow-graph/ui/WorkflowDefinitionNotice.tsx` — modes: `current` | `historical` | `historical-edited-since` | `legacy-unavailable` per FR-018e–g
- [x] T064 [US7] Update `WorkflowDetailPage.tsx` to pass `displayExecution?.steps_snapshot ?? detail.steps` into `WorkflowGraph` when a historical run is selected; show `WorkflowDefinitionNotice` above graph — depends on T062, T063
- [x] T065 [US7] Regenerate `@ze/client` after schema change — depends on T061
- [x] T066 [US7] Run quickstart.md Story 7 manually or via automated coverage; run `make test-automation test-personal test-api lint`

**Checkpoint**: Step edits + historical run review are trustworthy; UI never silently mislabels old runs as current definition.
