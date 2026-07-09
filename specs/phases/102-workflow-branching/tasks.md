---

description: "Task list for feature implementation"
---

# Tasks: Workflow Conditional Branching

**Input**: Design documents from `specs/phases/102-workflow-branching/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md (all present)

**Tests**: Included and REQUIRED — constitution Principle V (Test Discipline) is non-negotiable: no task is done until its tests exist and pass, mocking the DB (`AsyncMock`) and the LLM client, never hitting a real database or real OpenRouter call.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and testing of each story.

## Path Conventions

This is the existing Ze monorepo — no new packages. Paths used below:

- `core/ze-automation/ze_automation/workflow/` — engine types/planner/store (no domain knowledge)
- `core/ze-automation/ze_automation/agents/workflow/` — agent tool surface
- `core/ze-automation/tests/workflow_engine/`, `core/ze-automation/tests/workflow_agent/` — backend tests
- `plugins/ze-personal/ze_personal/graph/workflow.py` — execution graph (existing, pre-Phase-74-reorg location)
- `plugins/ze-personal/tests/graph/test_workflow.py` — execution graph tests
- `apps/ze-api/ze_api/api/` — REST schemas/routes
- `apps/ze-web/src/widgets/workflow-steps/`, `apps/ze-web/src/widgets/workflow-executions/` — existing UI widgets

---

## Phase 1: Setup

**Purpose**: Confirm environment readiness. This feature introduces no new dependencies, no new package, no new database migration.

- [X] T001 Confirm `make db-up`, `make dev`, `make test-automation`, `make test-personal`, and `make test-web` all run cleanly on the current branch before starting (baseline check — no code changes)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data model, persistence, and REST schema changes every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 Add `Branch` dataclass (`condition: str`, `to: str`) and extend `WorkflowStep` (+ `id: str`, `branches: list[Branch] = []`, `default_next: str | None = None`) and `StepResult` (+ `step_id: str`, `branch_taken: str | None = None`) in `core/ze-automation/ze_automation/workflow/types.py`
- [X] T003 [P] Extend `_step_to_dict`/`_step_from_dict` (backfill `id = f"s{index}"` when absent, requiring an `index` parameter) and `_step_result_to_dict`/`_step_result_from_dict` (new fields, absent-safe on read) in `core/ze-automation/ze_automation/workflow/postgres.py`
- [X] T004 [P] Add a branch/default-next target-validation helper (every `Branch.to`/`default_next` must equal `"END"`, `"FAIL"`, or another step's `id` in the same plan; unique `id`s) that raises the existing `WorkflowPlanError` in `core/ze-automation/ze_automation/workflow/planner.py`
- [X] T005 [P] Add `BranchResponse` model and extend `WorkflowStepResponse` (+ `id`, `branches`, `default_next`) and `StepResultResponse` (+ `step_id`, `branch_taken`) in `apps/ze-api/ze_api/api/schemas.py`
- [X] T006 Extend `get_workflow()` and `list_workflow_executions()` dict builders to include the new fields in `core/ze-automation/ze_automation/rest.py` (depends on T002)
- [X] T007 [P] Add unit tests for `Branch`/`WorkflowStep`/`StepResult` field defaults (empty `branches`, `None` `default_next`/`branch_taken` reproduce today's shape) in `core/ze-automation/tests/workflow_engine/test_types.py` (new file)
- [X] T008 [P] Add unit tests for id backfill (`"s{index}"` for steps missing `id`) and branch/default_next/step_id/branch_taken JSONB round-trip in `core/ze-automation/tests/workflow_engine/test_postgres_workflow_store.py`

**Checkpoint**: Data model, persistence, and REST schema are ready — user story work can begin.

---

## Phase 3: User Story 1 - Branch a workflow on step outcome (Priority: P1) 🎯 MVP

**Goal**: A step with branches routes to whichever branch's condition matches its output; a step with no branches behaves exactly as today.

**Independent Test**: Create a workflow with one branching step and two possible continuations; run it twice with inputs that force each outcome; verify each run completes via the correct path, with the other path's steps never executed.

### Tests for User Story 1

- [X] T009 [P] [US1] Add test: a step with two branches routes to the matching branch's target and the non-matching branch's target never executes, in `plugins/ze-personal/tests/graph/test_workflow.py`
- [X] T010 [P] [US1] Add test: a step with no branches continues to the next step in list order (regression against today's behavior), in `plugins/ze-personal/tests/graph/test_workflow.py`
- [X] T011 [P] [US1] Add test: a step with no branches but `default_next` set jumps to that target instead of the next step in list order (FR-006's no-branches override case), in `plugins/ze-personal/tests/graph/test_workflow.py`
- [X] T012 [P] [US1] Add test: a step whose own verification fails routes to `workflow_failed` and never reaches `route_branch`, even when that step has `branches` defined (FR-009 regression against the refactored routing path), in `plugins/ze-personal/tests/graph/test_workflow.py`
- [X] T013 [P] [US1] Add test: `create_workflow` rejects a plan containing a branch/default_next target that isn't an existing step id or `END`/`FAIL`, returning the existing `{"error": ...}` shape, in `core/ze-automation/tests/workflow_agent/test_tools.py`

### Implementation for User Story 1

- [X] T014 [US1] Add `current_step_id: str`, `steps_by_id: dict[str, WorkflowStep]` to `WorkflowAgentState`, built once from `workflow_steps` when a run starts, in `plugins/ze-personal/ze_personal/graph/workflow.py` (depends on T002)
- [X] T015 [US1] Implement the `route_branch` node: resolve output against `branches` in order via one `LLMClient.complete()` classification call (reusing the `workflow_verify` model config key), falling back to `default_next` then plain sequential order, in `plugins/ze-personal/ze_personal/graph/workflow.py` (depends on T014)
- [X] T016 [US1] Update `after_verify_step` and the graph builder's conditional edges to route through `route_branch`, handling `END`/`FAIL` terminal targets, in `plugins/ze-personal/ze_personal/graph/workflow.py` (depends on T015)
- [X] T017 [US1] Record `step_id` and `branch_taken` on every `StepResult` produced by `verify_step`/`_fail_step`, in `plugins/ze-personal/ze_personal/graph/workflow.py` (depends on T002, T016)
- [X] T018 [US1] Wire the T004 target-validation helper into `create_workflow`, immediately after `planner.plan()`, in `core/ze-automation/ze_automation/agents/workflow/tools.py` (depends on T004)

**Checkpoint**: User Story 1 is fully functional and testable independently — this is the MVP.

---

## Phase 4: User Story 2 - Repeat a step until a condition is met, safely (Priority: P2)

**Goal**: A branch may point backward to an earlier step (a loop), bounded so the run always terminates.

**Independent Test**: Create a workflow where a branch always routes back to an earlier step; run it; verify the workflow stops itself after a fixed number of repeats with a clear "loop limit exceeded" failure.

### Tests for User Story 2

- [X] T019 [P] [US2] Add test: a step whose branch always routes back to itself fails the run after its 4th execution (1 initial + 3 revisits), with an error naming the step and explaining the loop limit, in `plugins/ze-personal/tests/graph/test_workflow.py`
- [X] T020 [P] [US2] Add test: a loop that routes forward before the limit is hit continues normally past the loop, in `plugins/ze-personal/tests/graph/test_workflow.py`

### Implementation for User Story 2

- [X] T021 [US2] Add `visit_counts: dict[str, int]` to `WorkflowAgentState`; increment and check it in `route_branch` before advancing to a target, failing with a descriptive loop-limit error once a step's total execution count exceeds 4, in `plugins/ze-personal/ze_personal/graph/workflow.py` (depends on T015)

**Checkpoint**: User Stories 1 and 2 both work independently — branching and bounded looping are functional.

---

## Phase 5: User Story 3 - Existing workflows keep working unchanged (Priority: P1)

**Goal**: Workflows saved before this feature existed run identically after it ships — zero required migration, zero behavior change.

**Independent Test**: Take a workflow saved before this feature shipped, run it after, and confirm identical step order and pass/fail outcome.

### Tests for User Story 3

- [ ] T022 [P] [US3] Add test: a stored workflow row whose `steps` JSON has no `id`/`branches`/`default_next` keys loads via `_row_to_workflow` with ids backfilled as `s0, s1, ...` in list order and `branches == []` on every step, in `core/ze-automation/tests/workflow_engine/test_postgres_workflow_store.py`
- [ ] T023 [P] [US3] Add test: a legacy (backfilled, branch-less) workflow run executes every step in original order, and a failed step fails the whole run with no implicit branching or retry, in `plugins/ze-personal/tests/graph/test_workflow.py`
- [ ] T024 [P] [US3] Add test: `get_workflow`/`list_workflows` agent tools return a legacy workflow's steps with backfilled ids and empty `branches`, indistinguishable in shape from a newly authored linear workflow, in `core/ze-automation/tests/workflow_agent/test_tools.py`

**Checkpoint**: User Story 3 verified — no implementation tasks beyond Foundational; this phase is pure regression coverage confirming T002/T003/T014–T017 didn't change legacy behavior.

---

## Phase 6: User Story 4 - Workflow authoring can optionally describe branches (Priority: P3)

**Goal**: `WorkflowPlanner` can emit branches when a description implies a conditional outcome, and continues to emit plain linear plans otherwise.

**Independent Test**: Submit a description with an explicit either/or condition and confirm the resulting workflow has a branching step; submit a plain linear description and confirm no branches.

### Tests for User Story 4

- [ ] T025 [P] [US4] Add test: `WorkflowPlanner.plan()` given a description with explicit either/or conditional language returns steps including a non-empty `branches` list (mock `LLMClient.complete` to return a fixed branching JSON payload), in `core/ze-automation/tests/workflow_engine/test_workflow_planner.py`
- [ ] T026 [P] [US4] Add test: `WorkflowPlanner.plan()` given a plain sequential description returns steps with `branches == []` on every step (regression), in `core/ze-automation/tests/workflow_engine/test_workflow_planner.py`

### Implementation for User Story 4

- [ ] T027 [US4] Extend `_PLAN_SYSTEM` to optionally request `id`, `branches` (list of `{condition, to}`), and `default_next` per step, instructing the model to omit them for plain linear workflows, in `core/ze-automation/ze_automation/workflow/planner.py` (depends on T004)
- [ ] T028 [US4] Extend `WorkflowPlanner.plan()`'s JSON parsing to build `Branch` objects and populate the new `WorkflowStep` fields, defaulting to `id=f"s{index}"`, `branches=[]`, `default_next=None` when the model omits them, in `core/ze-automation/ze_automation/workflow/planner.py` (depends on T002, T027)

**Checkpoint**: All backend user stories (1–4) are independently functional.

---

## Phase 7: User Story 5 - The existing Workflows screen stays accurate for branching and looping runs (Priority: P1)

**Goal**: The already-shipped Workflows screen (REST-backed) renders branching/looping runs correctly instead of relying on the array-position assumption this feature removes.

**Independent Test**: Run a branching workflow where one of two steps is skipped; confirm the Workflows screen shows only the executed step as completed and the skipped one as "not taken this run." Run a looping workflow; confirm repeated steps show as separate entries.

### Tests for User Story 5

- [ ] T029 [P] [US5] Add route test: `getWorkflow` and `listWorkflowExecutions` responses include `id`/`branches`/`default_next` and `step_id`/`branch_taken`, in `apps/ze-api/tests/api/test_workflows_route.py` (new file, following the `test_<name>_route.py` convention used by `test_channels_route.py`)
- [ ] T030 [P] [US5] Add component test: `WorkflowStepsList` renders rows in `step_results` execution order keyed by `step_id`, repeating a looped step as separate rows rather than collapsing to one, in `apps/ze-web/src/widgets/workflow-steps/ui/WorkflowStepsList.test.tsx` (new file)
- [ ] T031 [P] [US5] Add component test: a step absent from the executed `step_id` set renders as "not taken this run" (visually distinct from pending/running/completed/failed) on a completed or failed execution, and pre-existing non-branching workflows show zero visual change, in `apps/ze-web/src/widgets/workflow-steps/ui/WorkflowStepsList.test.tsx`
- [ ] T032 [P] [US5] Add component test: `LiveRunPanel` shows the fixed "N / total" header for a workflow with no branches, and a running-count-only header (no denominator) for a workflow with any step's `branches` non-empty, in `apps/ze-web/src/widgets/workflow-executions/ui/LiveRunPanel.test.tsx` (new file)

### Implementation for User Story 5

- [ ] T033 [US5] Run `make codegen` to regenerate `@myguyze/ze-client` after the T005 schema changes land, so `WorkflowStepResponse`/`StepResultResponse` TypeScript types include the new fields
- [ ] T034 [US5] Rewrite `WorkflowStepsList` to iterate `execution.step_results` (execution order) keyed by `step_id`, looking up static step metadata (`task`, `agent_hint`, ...) from a `Map<string, WorkflowStepResponse>` built from `workflow.steps` by `id`, falling back to rendering `workflow.steps` in authored order only when no execution exists yet, in `apps/ze-web/src/widgets/workflow-steps/ui/WorkflowStepsList.tsx` (depends on T033)
- [ ] T035 [US5] Add the `"not-taken"` `StepState` value and its resolution rule (a step's `id` absent from the executed-`step_id` set on a completed/failed, non-running execution resolves to `"not-taken"`, distinct from `"pending"`) with its dimmed + labeled visual treatment, in `apps/ze-web/src/widgets/workflow-steps/ui/WorkflowStepsList.tsx` (depends on T034)
- [ ] T036 [US5] Apply the same execution-order/`step_id` rendering fix and `"not-taken"` state to `LiveRunPanel`, in `apps/ze-web/src/widgets/workflow-executions/ui/LiveRunPanel.tsx` (depends on T033)
- [ ] T037 [US5] Change `LiveRunPanel`'s header to a running-count-only display (no denominator) when `workflow.steps.some(s => s.branches.length > 0)` — `default_next` alone does not count, per FR-017 — keeping the existing fixed "N / total" form otherwise, in `apps/ze-web/src/widgets/workflow-executions/ui/LiveRunPanel.tsx` (depends on T036)

**Checkpoint**: All five user stories are independently functional; the existing Workflows screen is accurate for every workflow shape.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Repo-wide close-out per constitution's Definition of Done.

- [ ] T038 [P] Update `spec.md`'s `**Status**` field from `Draft` to `Implemented` in `specs/phases/102-workflow-branching/spec.md`, in the same commit as the implementation (constitution Principle I)
- [ ] T039 [P] Add the phase 102 index row to `specs/README.md`
- [ ] T040 Run every scenario in `specs/phases/102-workflow-branching/quickstart.md` end-to-end (`make dev-full`) and confirm expected outcomes
- [ ] T041 Run `make lint`, `make test-automation`, `make test-personal`, and `make test-web`; fix any failures

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Story 1 (Phase 3, P1)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4, P2)**: Depends on Foundational **and** User Story 1's `route_branch` node (T015) — looping is explicitly a branch pointing backward, so it reuses US1's routing mechanism rather than duplicating it.
- **User Story 3 (Phase 5, P1)**: Depends on Foundational only for its own correctness (id backfill, empty-branches default) — independently testable without US1/US2, though it's ordered after them here since it's pure regression coverage best run once the engine changes exist.
- **User Story 4 (Phase 6, P3)**: Depends on Foundational only (the `Branch` dataclass and target-validation helper). Independently testable without US1/US2/US3.
- **User Story 5 (Phase 7, P1)**: Depends on Foundational (T005/T006 schema fields must exist for the types to be meaningful). Independently testable with fixture data alone, though full manual verification per quickstart.md benefits from US1/US2 being done (real branching/looping runs to inspect).
- **Polish (Phase 8)**: Depends on all desired user stories being complete.

### Parallel Opportunities

- T003, T004, T005, T007, T008 (Foundational, marked [P]) can run in parallel once T002 lands (T003/T006/T007/T008 touch different files than T002; T004/T005 are fully independent of each other and of T002's file).
- Within User Story 1: T009, T010, T011, T012 (tests, same file — independent test functions, same convention as the rest of this phase) and T013 (tests, different file) can all run in parallel; T014→T015→T016→T017 are sequential (same file, each depends on the last); T018 can run in parallel with the T014–T017 chain (different file).
- Within User Story 2: T019, T020 (tests) in parallel; T021 is a single sequential task.
- Within User Story 3: T022, T023, T024 (tests, three different files) fully in parallel — no implementation tasks in this phase.
- Within User Story 4: T025, T026 (tests) in parallel; T027→T028 sequential (same file).
- Within User Story 5: T029, T030, T031, T032 (tests, three different files — note T030/T031 share `WorkflowStepsList.test.tsx` so are sequential with each other, not parallel) can mostly run in parallel; T034→T035 sequential (same file), T036→T037 sequential (same file), but the `WorkflowStepsList.tsx` pair (T034/T035) and the `LiveRunPanel.tsx` pair (T036/T037) can run in parallel with each other once T033 (codegen) completes.
- Once User Stories 1–4 (backend) are done, User Story 5 (frontend) tests/implementation can proceed in parallel with any remaining backend polish.

---

## Parallel Example: Foundational Phase

```bash
# After T002 (types.py) lands, launch together:
Task: "Extend _step_to_dict/_step_from_dict/_step_result_(to|from)_dict in core/ze-automation/ze_automation/workflow/postgres.py"
Task: "Add branch/default-next target-validation helper in core/ze-automation/ze_automation/workflow/planner.py"
Task: "Add BranchResponse + extend WorkflowStepResponse/StepResultResponse in apps/ze-api/ze_api/api/schemas.py"
Task: "Add unit tests for Branch/WorkflowStep/StepResult defaults in core/ze-automation/tests/workflow_engine/test_types.py"
```

## Parallel Example: User Story 1

```bash
Task: "Test: branching step routes to matching branch, skips the other — plugins/ze-personal/tests/graph/test_workflow.py"
Task: "Test: no-branches step continues sequentially (regression) — plugins/ze-personal/tests/graph/test_workflow.py"
Task: "Test: no-branches step with default_next jumps to that target — plugins/ze-personal/tests/graph/test_workflow.py"
Task: "Test: a failed step never reaches route_branch — plugins/ze-personal/tests/graph/test_workflow.py"
Task: "Test: create_workflow rejects invalid branch target — core/ze-automation/tests/workflow_agent/test_tools.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (blocks everything)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart.md's Section 1 scenario independently
5. Deploy/demo if ready — a workflow can branch, even without looping, planner authoring, or the UI fix yet

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. User Story 1 → branching works (MVP)
3. User Story 2 → looping is bounded and safe
4. User Story 3 → legacy workflows verified unaffected
5. User Story 4 → natural-language authoring can produce branches
6. User Story 5 → existing Workflows screen stays accurate
7. Polish → status/index updated, full quickstart run, lint + full test suite green

### Suggested Solo Sequencing

Given this is a single-contributor feature (no parallel team), the phase order above (1→2→3→4→5→6→7→8) is also the recommended build order: it front-loads the highest-risk, highest-priority work (branching execution, then its immediate loop-guard extension) before the lower-priority planner-authoring convenience (US4, P3) and the UI correctness fix (US5), which is safest to verify last since it benefits from having real branching/looping runs already producible via the agent tools.

---

## Notes

- [P] tasks = different files, no unmet dependencies within their phase (or independent test functions within the same file, consistent with this project's existing test style).
- [Story] label maps each task to its user story for traceability back to spec.md.
- Every user story phase includes its own tests per constitution Principle V — write and run them against the implementation in the same phase; do not defer test-writing to Phase 8.
- Mock `LLMClient.complete` and the asyncpg pool (`AsyncMock`) in every new/extended test — no real DB, no real LLM call, per constitution Principle V.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
- User Story 3 (Phase 5) intentionally has no implementation tasks — it exists to prove the Foundational + US1/US2 changes didn't regress legacy behavior (SC-002), not to add new code.
- T011 and T012 (US1) were added by the `/speckit-analyze` pass to close two coverage gaps: FR-006's "no branches + default_next" case, and FR-009's failure-precedes-branch-evaluation invariant against the refactored routing path.
