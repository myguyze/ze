# Implementation Plan: Workflow Revision Audit

**Branch**: `108-workflow-revision-audit` | **Date**: 2026-07-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/phases/108-workflow-revision-audit/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Append an immutable `workflow_revisions` row every time a workflow is created or its
step list is replaced, capturing before/after steps, a human-readable change summary,
and actor context (agent+chat session/message id, or API). Expose the log via
`GET /api/v0/workflows/{workflow_id}/revisions` (offset-paginated, newest first) and
render it as a new "Change History" section on the workflow detail page, with a
"View conversation" deep link for chat-originated edits and a link from the existing
107b `WorkflowDefinitionNotice` banner to post-run revisions.

The write path is a single hook inside `PostgresWorkflowStore.create` /
`.update_steps`, so both the `edit_workflow_steps` agent tool and the
`PATCH /{workflow_id}/steps` REST route go through it automatically (FR-013) without
touching call sites beyond passing actor context down.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5 / React 18 (ze-web)

**Primary Dependencies**: FastAPI, asyncpg, Alembic (raw SQL), LangGraph
(`config["configurable"]` for actor-context threading), `@tanstack/react-query`,
`@myguyze/ze-client` (OpenAPI-codegen'd client)

**Storage**: PostgreSQL — new `workflow_revisions` table in the `ze-automation`
package's `zc` migration chain (continues from `zc025`)

**Testing**: pytest (`make test-automation`, `make test-api`), vitest
(`make test-web`)

**Target Platform**: Existing Ze backend (`apps/ze-api`) + React web client

**Project Type**: Web application (FastAPI backend + React frontend), extending an
existing feature area (workflows)

**Performance Goals**: N/A — low-volume, per-workflow audit log; no new hot path

**Constraints**: Revision write must be atomic with the `workflows` UPDATE/INSERT it
audits (same connection/transaction); no revision on validation failure or no-op
edits (FR-008); revisions cascade-delete with their workflow (FR-014)

**Scale/Scope**: Single-user; revision volume bounded by manual/agent edit frequency
per workflow (tens, not thousands, per workflow) — offset pagination is sufficient,
matching the `goal_execution_traces` precedent

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-First Development**: Spec at `specs/phases/108-workflow-revision-audit/spec.md`
  is clarified and checklist-complete. PASS.
- **II. Single-User Model**: No `user_id` columns. `session_id`/`user_message_id` are
  conversation-linkage, not tenant scoping. PASS.
- **III. Layered Package Architecture**: New table + store methods live in
  `core/ze-automation` (already owns `workflows`/`workflow_executions`). REST route
  added to existing `apps/ze-api` router. No plugin boundary crossed. PASS.
- **IV. Typed, Explicit Python**: New `WorkflowRevision`/`ActorContext` dataclasses in
  `workflow/types.py`; Pydantic response models only in `ze_api/api/schemas.py`.
  Errors reuse existing `WorkflowPlanError` (no new error type needed — writes never
  fail the caller; a revision-write failure must not break the underlying edit, see
  research.md). PASS.
- **V. Test Discipline**: New tests in `core/ze-automation/tests/workflow/` (store),
  `apps/ze-api/tests/` (route), `apps/ze-web/src/pages/workflow-detail/` (component).
  No real DB/LLM in unit tests. PASS.
- **VI. Explicit Persistence**: Hand-written raw-SQL Alembic migration
  `zc026_workflow_revisions.py` in `core/ze-automation`, `down_revision = "zc025"`,
  FK `ON DELETE CASCADE` to `workflows.id`. PASS.
- **VII. One LLM Gateway, Local Embeddings**: Not applicable — no LLM calls added.
  PASS.

No violations. Complexity Tracking section not needed.

## Project Structure

### Documentation (this feature)

```text
specs/phases/108-workflow-revision-audit/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/
│   └── workflow-revisions-api.md
└── tasks.md              # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
core/ze-automation/ze_automation/
├── workflow/
│   ├── types.py                # + WorkflowRevision, ActorContext, ActorSource
│   ├── store.py                # + WorkflowStore.list_revisions(), record_revision() internal
│   ├── postgres.py              # + revision write inside create()/update_steps(); + list_revisions()
│   ├── revision_summary.py      # NEW — before/after step diff → human-readable summary (FR-007)
├── agents/workflow/
│   └── tools.py                  # edit_workflow_steps/create_workflow gain session_id/user_message_id params
├── rest.py                        # + list_workflow_revisions()
└── migrations/versions/
    └── zc026_workflow_revisions.py   # NEW

core/ze-agents/ze_agents/
└── types.py                       # AgentContext.extensions carries user_message_id (no new field)

core/ze-core/ze_core/orchestration/nodes/
└── context.py                     # fetch_context reads configurable["user_message_id"]

apps/ze-api/ze_api/api/
├── websocket/turns.py             # config_extra["user_message_id"] = str(user_msg.id)
├── routes/workflows.py            # + GET /{workflow_id}/revisions
└── schemas.py                     # + WorkflowRevisionResponse, ActorContextResponse

apps/ze-web/src/
├── entities/workflow/
│   ├── api/useWorkflowRevisionsQuery.ts   # NEW
│   └── index.ts                            # export it
├── widgets/workflow-graph/ui/
│   └── WorkflowDefinitionNotice.tsx        # + link to filtered revisions (Story 4)
└── pages/workflow-detail/ui/
    └── WorkflowDetailPage.tsx              # + "Change History" SectionPanel
```

**Structure Decision**: Option 2 (web application: FastAPI backend + React frontend),
extending the existing `ze-automation` / `ze-api` / `ze-web` workflow feature area in
place — no new packages, no new plugin.

## Complexity Tracking

> No Constitution Check violations — section intentionally empty.
