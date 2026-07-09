# Implementation Plan: Workflow Conditional Branching

**Branch**: `102-workflow-branching` | **Date**: 2026-07-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/phases/102-workflow-branching/spec.md`

## Summary

Give workflow steps a stable id and an optional ordered list of natural-language
branches (condition → target step id / END / FAIL) plus a default-next override, so
a workflow can route conditionally instead of always advancing sequentially. Add a
bounded loop guard (default: initial visit + 3 revisits = 4 total executions per
step per run) so a backward-pointing branch can express retry/repeat-until-done
behavior without risking an infinite run. Extend `WorkflowPlanner` to optionally
emit branches from natural-language descriptions containing conditional language,
defaulting to today's linear plan when it doesn't. All of this is additive to the
existing JSONB-backed `Workflow`/`WorkflowStep`/`StepResult` types, so pre-existing
persisted workflows keep running unchanged (ids backfilled at read time, empty
branch lists preserve current linear behavior exactly).

**Scope correction (added after initial planning)**: Ze already has a live REST
API (`ze_api/api/routes/workflows.py`) and a shipped web UI (`pages/workflows`,
`pages/workflow-detail`, `widgets/workflow-steps`, `widgets/workflow-executions`)
for viewing workflows and their run history. Two of those widgets
(`WorkflowStepsList`, `LiveRunPanel`) render a run by assuming `StepResult.step_index`
equals the step's position in the static `steps` array and that every step runs
exactly once, in array order. Branching/looping breaks that assumption. This plan
therefore also: (a) extends the REST schemas to carry the new fields, and (b) fixes
both widgets to render by actual execution order and `step_id` instead of static
array position — otherwise the already-shipped UI would silently mis-render any
branching or looping run (User Story 5, FR-014/FR-015, SC-006). A second
clarification round resolved two remaining UX questions this raised: a step not
on the executed path is shown dimmed/labeled "not taken this run" rather than
omitted or shown as pending (FR-016), and the live "Step N / total" indicator
drops its fixed denominator — showing a running count only — for any workflow
that has branches anywhere, since the total steps on the eventual path can't be
known until the run resolves (FR-017). Non-branching workflows keep today's
fixed-denominator indicator unchanged.

## Technical Context

**Language/Version**: Python 3.12 (project floor: >=3.11)

**Primary Dependencies**: LangGraph (workflow execution graph), `ze_agents.client.LLMClient`
over OpenRouter (branch classification + existing verify-gate calls), asyncpg
(existing `workflows`/`workflow_executions` tables), FastAPI + Pydantic (existing
`ze_api/api/routes/workflows.py` + `schemas.py`), React/TanStack Query + the
codegen'd `@myguyze/ze-client` SDK (existing `ze-web` Workflows screen)

**Storage**: PostgreSQL — `workflows.steps` and `workflow_executions.step_results`
are already `jsonb` columns (`core/ze-automation/ze_automation/workflow/postgres.py`).
New step/result fields are additive JSON keys; **no schema migration is required**.

**Testing**: pytest, `asyncio_mode = "auto"`; mock `LLMClient.complete` (branch
classification is just another judge-style call) and mock asyncpg pool with
`AsyncMock`, per constitution V. No real DB, no real LLM in unit tests.

**Target Platform**: Linux server (`ze-api` backend) plus the existing `ze-web`
SPA. No *new* UI surface is built (no graph editor) — but the existing Workflows
screen's two run-rendering widgets require a correctness fix, per User Story 5.

**Project Type**: Backend feature within the existing Python monorepo, plus a
targeted fix to two already-existing `ze-web` widgets and their REST-backed types.
No new service, no new package, no new page/route.

**Performance Goals**: A step with no branches must incur exactly the same number
of LLM calls as today (zero additional calls) — branch classification only runs
for steps that declare `branches`. No new throughput/latency target beyond "no
regression for non-branching workflows."

**Constraints**: No new Alembic migration (additive JSONB fields only); 100%
behavioral compatibility for pre-existing workflows (SC-002); loop bounded to 4
total executions of a given step per run by default (per clarification), not
configurable per-workflow in this iteration.

**Scale/Scope**: Single-user assistant; workflows remain small (single digits to
low tens of steps). No concurrency/scale concerns — one workflow run executes one
step at a time, unchanged from today.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|---|---|
| I. Spec-First Development | Spec at `specs/phases/102-workflow-branching/spec.md`; status will move from Draft → Implemented in the same commit as the code, per constitution. **PASS** |
| II. Single-User Model | No `user_id`/tenancy/role concept introduced anywhere in this feature. **PASS** |
| III. Layered Package Architecture | `WorkflowStep`/`Branch`/`StepResult`/`WorkflowPlanner`/`PostgresWorkflowStore` all stay in `core/ze-automation` (no domain knowledge — pure engine types), unchanged ownership. The execution graph (`route_branch` node) stays in `plugins/ze-personal/ze_personal/graph/workflow.py`, its current (pre-existing) location — see note below. **PASS**, with a flagged pre-existing inconsistency, not introduced by this plan. |
| IV. Typed, Explicit Python | `Branch` is a new dataclass in `types.py` (never `models.py`); invalid branch/default-next targets raise the existing typed `WorkflowPlanError` (`ze_agents.errors`), not a bare exception. **PASS** |
| V. Test Discipline | New tests added to `core/ze-automation/tests/workflow_engine/` and `plugins/ze-personal/tests/graph/test_workflow.py`; mock `LLMClient.complete` and asyncpg pool; no real DB/LLM. **PASS** |
| VI. Explicit Persistence | No migration: `steps`/`step_results` are already `jsonb`; new fields are additive keys handled entirely in Python (de)serialization. **PASS** |
| VII. One LLM Gateway, Local Embeddings | Branch classification is one more `LLMClient.complete()` call through the same injected client and `workflow_verify` model config key already used by the verify gate — no new provider, no new API key. **PASS** |
| Additional Constraints — Frontend FSD | The two widget fixes (`WorkflowStepsList`, `LiveRunPanel`) stay in their existing `widgets/` slice, importing types from `@myguyze/ze-client` as today (no new re-export wrapper). No new query hooks needed — existing `useWorkflowExecutionsQuery`/`useLiveExecutionQuery` already return the extended `WorkflowExecutionResponse` once the schema/codegen changes land. **PASS** |

**Note on III**: `plugins/ze-personal/ze_personal/graph/workflow.py` carries a
stale docstring ("Transitional location... once ze-personal package is created")
left over from the Phase 74 automation-substrate reorg — the workflow execution
graph arguably belongs in `ze-automation` itself now that package exists. Moving
it is out of scope for this feature (it's a pure relocation with no behavior
change); this plan extends the file in its current location and flags the
relocation as a follow-up cleanup.

No violations requiring justification — Complexity Tracking table is empty.

## Project Structure

### Documentation (this feature)

```text
specs/phases/102-workflow-branching/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   ├── workflow-tools.md    # Phase 1 output — affected agent-tool contracts
│   └── workflow-rest-api.md # Phase 1 output — affected REST endpoint/schema contracts
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
core/ze-automation/ze_automation/workflow/
├── types.py             # + Branch dataclass; WorkflowStep gains id/branches/default_next;
│                         #   StepResult gains step_id/branch_taken
├── planner.py            # _PLAN_SYSTEM extended to optionally emit id/branches/default_next;
│                         #   new target-validation helper reused by tools.py
├── postgres.py            # _step_to_dict/_step_from_dict/_step_result_(to|from)_dict extended;
│                         #   id backfill ("s{index}") for rows missing an id
└── store.py               # WorkflowStore protocol — unchanged signatures

core/ze-automation/ze_automation/agents/workflow/
└── tools.py              # create_workflow validates branch/default_next targets after
                           #   planner.plan(), raising WorkflowPlanError on invalid target;
                           #   get_workflow includes branches in its step serialization

plugins/ze-personal/ze_personal/graph/
└── workflow.py            # WorkflowAgentState: current_step_id, steps_by_id, visit_counts
                           #   (replacing current_step_index as the source of truth);
                           #   new route_branch node + conditional edges;
                           #   verify_step / after_verify_step updated to route through it

core/ze-automation/tests/workflow_engine/
├── test_workflow_planner.py     # + branch-emission cases
└── test_postgres_workflow_store.py  # + id backfill, branch/default_next round-trip

plugins/ze-personal/tests/graph/
└── test_workflow.py       # + branch routing, loop-guard, legacy-workflow compatibility cases

apps/ze-api/ze_api/api/
├── schemas.py             # WorkflowStepResponse +id/branches/default_next;
│                          #   StepResultResponse +step_id/branch_taken
└── routes/workflows.py    # no signature changes — response_model fields flow through

core/ze-automation/ze_automation/
└── rest.py                # get_workflow()/list_workflow_executions() dict-building
                           #   extended with the same new fields, mirrored from postgres.py

apps/ze-web/src/
├── entities/workflow/     # no changes — query hooks are generic passthroughs;
│                          #   @myguyze/ze-client regenerated via `make codegen`
└── widgets/
    ├── workflow-steps/ui/WorkflowStepsList.tsx      # render by execution order (step_results,
    │                                                 #   keyed by step_id) instead of static
    │                                                 #   steps.map(...) + step_index-as-position;
    │                                                 #   new "not-taken" StepState for steps absent
    │                                                 #   from the executed path (FR-016)
    └── workflow-executions/ui/LiveRunPanel.tsx       # same execution-order/step_id fix; "not-taken"
                                                       #   state; "Step N / total" → running-count-only
                                                       #   when workflow.steps has any branches (FR-017)
```

**Structure Decision**: No new packages, services, pages, or routes. Backend
changes land inside the existing `core/ze-automation` (types/planner/store/rest —
engine-owned, no domain knowledge), the existing `plugins/ze-personal` graph
module (execution), and the existing `ze-api` REST layer (schema/route). Frontend
changes are confined to two already-existing `widgets/` components — no new
entity, no new page, no new query hook. This mirrors how the linear workflow
engine and its UI are split today; the branching feature adds fields, one new
graph node, and a rendering-order fix rather than a new architectural layer.

## Complexity Tracking

*No violations — table intentionally empty.*
