# Implementation Plan: Workflow Resilience and Control

**Branch**: `107-workflow-resilience` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/phases/107-workflow-resilience/spec.md`

## Summary

Workflow execution today fails the entire run on any step verification failure (`after_verify_step` → `workflow_failed`), discards successful step output in `workflow_failed`, has no step-level retry beyond OpenRouter's internal client retries, treats "no results" like malfunction in verify/planner prompts, exposes `update_workflow` for schedule-only edits, and offers no cancellation once `trigger_now` fires. This phase adds: per-step `on_failure` routing (`fail` | `continue` | `skip_to:<step_id>`) reusing existing branch/next-step machinery; automatic transient retries (2 retries / 3 attempts, system default); partial-result synthesis in the existing failure notification path; monitoring-aware verify criteria and a `no_results` step-result flag; REST + agent-tool step editing with validation; and run cancellation (REST + agent tool + ze-web cancel button) with a new `cancelled` execution status. Steps and step results remain JSONB on existing tables — no schema migration.

## Technical Context

**Language/Version**: Python 3.11 (`core/ze-automation`, `plugins/ze-personal`), TypeScript/React (`apps/ze-web`)

**Primary Dependencies**: LangGraph workflow graph (`plugins/ze-personal/ze_personal/graph/workflow.py`), `WorkflowScheduler` / `PostgresWorkflowStore` (`core/ze-automation`), FastAPI REST (`apps/ze-api`), OpenRouter client (existing internal retries — workflow-level retries are an additional layer at step boundaries), `ProactiveNotifier` failure alerts (`core/ze-automation/ze_automation/bootstrap.py`)

**Storage**: PostgreSQL — existing `workflows.steps` and `workflow_executions.step_results` JSONB columns; new fields (`on_failure`, `attempt_count`, `no_results`) stored inside those JSON blobs. New execution status string `cancelled`. No Alembic migration.

**Testing**: pytest — `make test-automation`, `make test-personal` (workflow graph tests in `plugins/ze-personal/tests/graph/test_workflow.py`), `make test-api` for REST routes. Mock asyncpg pools and `client.complete`. No real DB or OpenRouter.

**Target Platform**: Backend (`apps/ze-api`, uvicorn); web client workflow detail page (`apps/ze-web/src/pages/workflow-detail/`).

**Project Type**: Monorepo extension — changes in `core/ze-automation` (types, store, scheduler, planner, agent tools, retry helper), `plugins/ze-personal` (workflow graph nodes/edges), `apps/ze-api` (REST + schemas), `apps/ze-web` (cancel button + execution status display).

**Performance Goals**: SC-006 — cancellation observed within a few seconds (checked at step boundaries, not mid-LLM-call). Retry backoff: fixed 2s delay between step attempts (research.md item 4) to avoid hammering rate limits.

**Constraints**: Single-user model; cancellation best-effort at step boundaries (spec Assumption). In-progress runs snapshot `workflow.steps` at executor invoke time (already true in `bootstrap._workflow_executor`). Step-editing UI out of scope — web is cancel-only.

**Scale/Scope**: ~15 files across 4 packages; primary complexity in workflow graph edge routing (`after_verify_step`, new `handle_step_failure` node) and scheduler cancellation registry.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-First Development** — Spec with 5 clarifications at `specs/phases/107-workflow-resilience/spec.md`. PASS.
- **II. Single-User Model** — No `user_id` columns; cancellation registry is process-local, not per-user. PASS.
- **III. Layered Package Architecture** — Domain workflow graph stays in `plugins/ze-personal`; automation substrate (types, store, scheduler, planner, tools) in `core/ze-automation`; REST in `apps/ze-api`. No plugin imports `ze_core` beyond existing graph wiring. PASS.
- **IV. Typed, Explicit Python** — New fields on existing dataclasses in `ze_automation/workflow/types.py`; Pydantic only in `ze_api/api/schemas.py` for REST. Errors via `WorkflowPlanError` / `WorkflowExecutionError`. PASS.
- **V. Test Discipline** — Graph routing, retry classification, on_failure policies, partial synthesis, store validation, REST cancel/edit covered in unit tests. PASS.
- **VI. Explicit Persistence** — JSONB field extensions only; no migration. PASS.
- **VII. One LLM Gateway** — Verify, synthesis, planner prompts unchanged gateway; retries reuse existing OpenRouter path. PASS.

No violations. Complexity Tracking section is empty.

## Project Structure

### Documentation (this feature)

```text
specs/phases/107-workflow-resilience/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── rest-api.md
│   └── internal-module-contracts.md
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
core/ze-automation/ze_automation/
├── workflow/
│   ├── types.py              # + on_failure on WorkflowStep; + attempt_count, no_results on StepResult
│   ├── postgres.py           # serialize/deserialize new fields; + update_steps()
│   ├── store.py              # Protocol: update_steps()
│   ├── planner.py            # _PLAN_SYSTEM: on_failure + monitoring verify guidance; validate skip_to
│   ├── scheduler.py          # CancellationRegistry; cancel_execution(); check between steps
│   ├── retry.py              # NEW — is_transient_failure(); STEP_MAX_ATTEMPTS = 3
│   └── validation.py         # NEW — validate_workflow_steps() shared by store + REST + tools
├── agents/workflow/tools.py  # edit_workflow_steps tool; cancel_workflow_run tool
├── bootstrap.py              # failure handler reads execution.summary for partial synthesis
└── rest.py                   # update_workflow_steps(); cancel_workflow_execution()

plugins/ze-personal/ze_personal/graph/
└── workflow.py               # handle_step_failure node; retry loop state; verify no_results;
                              # workflow_failed partial synthesis; cancellation checks;
                              # after_verify_step routing change

apps/ze-api/ze_api/api/
├── routes/workflows.py       # PATCH steps; POST cancel execution
└── schemas.py                # on_failure, attempt_count, no_results; request/response models

apps/ze-web/src/
├── entities/workflow/api/    # useUpdateWorkflowStepsMutation; useCancelExecutionMutation
└── pages/workflow-detail/    # Cancel button when running; cancelled status badge
```

**Structure Decision**: No new package. Workflow graph changes live in `plugins/ze-personal` (existing location per phase 74/20 reorg). Automation types/store/scheduler extensions in `core/ze-automation`. REST and minimal web UI in `apps/`.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
