---

description: "Task list for Workflow Revision Audit (Phase 108)"
---

# Tasks: Workflow Revision Audit

**Input**: Design documents from `/specs/phases/108-workflow-revision-audit/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/workflow-revisions-api.md, quickstart.md

**Tests**: Included — Constitution Principle V ("Test Discipline (NON-NEGOTIABLE)") requires every feature to ship with tests; `make test-<package>` and `make lint` must pass.

**Organization**: Tasks are grouped by user story (spec.md) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps to spec.md user stories (US1–US4)

## Path Conventions (per plan.md)

- Backend domain: `core/ze-automation/ze_automation/workflow/`, `core/ze-automation/ze_automation/agents/workflow/`, `core/ze-automation/ze_automation/migrations/versions/`
- Cross-package plumbing: `core/ze-core/ze_core/orchestration/nodes/context.py`
- API composition root: `apps/ze-api/ze_api/api/`
- Frontend: `apps/ze-web/src/entities/workflow/`, `apps/ze-web/src/pages/workflow-detail/`, `apps/ze-web/src/widgets/workflow-graph/`, `apps/ze-web/src/widgets/chat-workspace/`, `apps/ze-web/src/entities/session/`

---

## Phase 1: Setup

**Purpose**: No new project scaffolding needed — this phase extends existing `ze-automation`/`ze-api`/`ze-web` packages in place. Nothing to do here beyond confirming the environment is ready.

- [X] T001 Run `make db-up && make migrate` to confirm the DB is on `zc025` (pre-phase baseline) before adding `zc026`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types, the migration, and the diff-summary function that every user story's write and read paths depend on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T002 [P] Add `zc026_workflow_revisions.py` migration (down_revision `zc025`) creating `workflow_revisions` per data-model.md schema (UUID PK, `workflow_id` FK `ON DELETE CASCADE`, `revision_number`, `change_type` CHECK, `steps_before`/`steps_after` JSONB, `summary`, `actor_source` CHECK, `actor_session_id`, `actor_user_message_id`, `created_at`, unique index on `(workflow_id, revision_number)`, index on `(workflow_id, created_at DESC)`) in `core/ze-automation/ze_automation/migrations/versions/zc026_workflow_revisions.py`
- [X] T003 [P] Add `ActorSource` enum, `ActorContext` dataclass, and `WorkflowRevision` dataclass to `core/ze-automation/ze_automation/workflow/types.py`
- [X] T004 [P] Create `core/ze-automation/ze_automation/workflow/revision_summary.py` with `build_change_summary(before: list[WorkflowStep], after: list[WorkflowStep], change_type: str) -> str` implementing the per-step-id add/remove/field-change diff from research.md §3
- [X] T005 Add `list_revisions(workflow_id, limit=20, offset=0) -> list[WorkflowRevision]` to the `WorkflowStore` Protocol in `core/ze-automation/ze_automation/workflow/store.py`, and extend `create`/`update_steps` signatures with `actor: ActorContext | None = None` (depends on T003)
- [X] T006 [P] Unit tests for `build_change_summary` (add/remove/field-change/created cases, including the exact `"Step s1: on_failure fail → continue"` phrasing) in `core/ze-automation/tests/workflow/test_revision_summary.py` (depends on T004)

**Checkpoint**: Migration, types, and diff logic exist — user story implementation can begin.

---

## Phase 3: User Story 1 — Every definition change is recorded (Priority: P1) 🎯 MVP

**Goal**: Every successful workflow creation and step-list replacement (agent tool or REST) writes exactly one immutable revision row with actor context; failed/no-op edits write none.

**Independent Test**: Create a workflow via the workflow agent, edit one step's failure policy via chat, then query the store directly (`list_revisions`) and verify two rows: `created` with empty `steps_before`, and `edited` with correct `steps_before`/`steps_after` and agent actor context.

### Tests for User Story 1

- [X] T007 [P] [US1] Test `PostgresWorkflowStore.create` writes a `change_type="created"` revision with `revision_number=1`, empty `steps_before`, and the given `actor` in `core/ze-automation/tests/workflow/test_postgres_revisions.py` (mocked asyncpg pool per Constitution V)
- [X] T008 [P] [US1] Test `PostgresWorkflowStore.update_steps` writes a `change_type="edited"` revision with correct `steps_before`/`steps_after`, incrementing `revision_number`, in the same test file
- [X] T009 [P] [US1] Test that after `update_steps` writes revision 2, revision 1's row (all fields) is byte-for-byte unchanged on read-back — immutability / read-after-write (SC-006) — in the same test file (depends on T007, T008)
- [X] T010 [P] [US1] Test `update_steps` writes **no** revision when incoming steps equal current steps (no-op, FR-008) in the same test file
- [X] T011 [P] [US1] Test `update_steps` writes **no** revision when `validate_workflow_steps` raises `WorkflowPlanError` (FR-008) in the same test file
- [X] T012 [P] [US1] Test revision rows are cascade-deleted when the parent workflow is deleted (FR-014) in the same test file
- [X] T013 [P] [US1] Test `edit_workflow_steps`/`create_workflow` tools construct `ActorContext(source=AGENT, session_id=..., user_message_id=...)` from injected deps and pass it to the store in `core/ze-automation/tests/agents/workflow/test_tools_revision_actor.py`
- [X] T014 [P] [US1] Test `_merge_deps` auto-injects `session_id`/`user_message_id` into `edit_workflow_steps`/`create_workflow` from the agent's `deps` dict (reuse existing `ze_agents` deps-injection test patterns) in `core/ze-agents/tests/test_base_agent_deps.py`

### Implementation for User Story 1

- [X] T015 [US1] Implement revision write inside `PostgresWorkflowStore.create()` in `core/ze-automation/ze_automation/workflow/postgres.py`: compute `revision_number=1`, `summary` via `build_change_summary([], steps, "created")`, insert into `workflow_revisions` on the same `conn`/transaction as the `workflows` INSERT (depends on T002, T003, T004)
- [X] T016 [US1] Implement revision write inside `PostgresWorkflowStore.update_steps()` in the same file: compare incoming vs. current `steps` via `_step_to_dict`, skip the revision insert on identical/invalid input, else compute next `revision_number` (`COALESCE(MAX(...), 0) + 1`), `summary` via `build_change_summary`, insert on the same `conn` as the `workflows` UPDATE (depends on T015)
- [X] T017 [US1] Implement `PostgresWorkflowStore.list_revisions()` (offset-paginated, `revision_number DESC`) in the same file (depends on T005)
- [X] T018 [US1] Add `session_id: str | None = None, user_message_id: str | None = None` params to `edit_workflow_steps` and `create_workflow` in `core/ze-automation/ze_automation/agents/workflow/tools.py`; construct `ActorContext(source=ActorSource.AGENT, ...)` (fallback to `ActorSource.SYSTEM` when either is `None`) and pass as `actor=` to `store.update_steps`/`store.create` (depends on T003, T015, T016)
- [X] T019 [US1] Add `"session_id": ctx.session_id, "user_message_id": ctx.extensions.get("user_message_id")` to the `deps` dict in `WorkflowManagerAgent.run()` in `core/ze-automation/ze_automation/agents/workflow/agent.py` (depends on T018)
- [X] T020 [US1] Add `config_extra["user_message_id"] = str(user_msg.id)` in `handle_message()` in `apps/ze-api/ze_api/api/websocket/turns.py` (right after `user_msg` is constructed/saved)
- [X] T021 [US1] Read `config["configurable"].get("user_message_id")` in `fetch_context()` in `core/ze-core/ze_core/orchestration/nodes/context.py` and set `agent_context.extensions["user_message_id"] = user_message_id` when present (depends on T020)
- [X] T022 [US1] Pass `actor=ActorContext(source=ActorSource.API)` from `update_workflow_steps()` in `core/ze-automation/ze_automation/rest.py` through to `store.update_steps(...)` (depends on T003, T016)

**Checkpoint**: Every create/edit path (agent + API) now produces exactly one correctly-attributed, immutable revision row, verifiable via `list_revisions` — User Story 1 is independently complete.

---

## Phase 4: User Story 2 — Review change history on the workflow page (Priority: P2)

**Goal**: The workflow detail page shows a reverse-chronological, human-readable "Change History" section, including an explicit empty/legacy state.

**Independent Test**: Edit a workflow twice, open its detail page, expand "Change history", verify newest-first entries with summaries and timestamps; on a workflow with zero revisions, verify the legacy empty state.

### Tests for User Story 2

- [X] T023 [P] [US2] Test `GET /api/v0/workflows/{id}/revisions` returns paginated `WorkflowRevisionResponse[]` newest-first and 404s for an unknown workflow in `apps/ze-api/tests/api/routes/test_workflows_revisions.py`
- [X] T024 [P] [US2] Component test: `WorkflowDetailPage` renders a "Change History" section with revision entries (number, timestamp, change-type badge, actor label, summary) and an expand-to-inspect before/after view in `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.test.tsx`
- [X] T025 [P] [US2] Component test: `WorkflowDetailPage` shows an explicit empty/legacy state when a workflow has zero revisions in the same test file

### Implementation for User Story 2

- [X] T026 [US2] Add `ActorContextResponse`/`WorkflowRevisionResponse` Pydantic models to `apps/ze-api/ze_api/api/schemas.py` per contracts/workflow-revisions-api.md (flattened `actor_*` fields)
- [X] T027 [US2] Add `list_workflow_revisions(store, workflow_id, limit, offset) -> list[dict]` to `core/ze-automation/ze_automation/rest.py`, serializing `WorkflowRevision` (reuse `_step_to_response_dict` for steps) (depends on T017)
- [X] T028 [US2] Add `GET /{workflow_id}/revisions` route (`operation_id="listWorkflowRevisions"`, `limit: Query(20, ge=1, le=100)`, `offset: Query(0, ge=0)`, 404 on missing workflow) to `apps/ze-api/ze_api/api/routes/workflows.py` (depends on T026, T027)
- [X] T029 [US2] Regenerate `@myguyze/ze-client` from the updated OpenAPI spec (per repo's existing codegen command) so `listWorkflowRevisions` and `WorkflowRevisionResponse` are available to ze-web (depends on T028)
- [X] T030 [P] [US2] Create `useWorkflowRevisionsQuery.ts` in `apps/ze-web/src/entities/workflow/api/` following the `useWorkflowExecutionsQuery.ts` pattern (`queryKeys.workflowRevisions(workflowId)`, `enabled: !!workflowId`) (depends on T029)
- [X] T031 [P] [US2] Add `workflowRevisions(workflowId)` key to `apps/ze-web/src/shared/lib/query-keys.ts`
- [X] T032 [US2] Export `useWorkflowRevisionsQuery` from `apps/ze-web/src/entities/workflow/index.ts` (depends on T030)
- [X] T033 [US2] Add a "Change History" `SectionPanel` to `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.tsx` (below "Run History" in the existing 3-column grid): list of revisions using `useWorkflowRevisionsQuery`, each row showing revision number, relative timestamp, change-type badge, actor label ("Ze" for `agent`/`system`, "API" for `api`), one-line summary, and an expand toggle revealing full `steps_before`/`steps_after`; explicit empty/legacy state when the list is empty (depends on T032)

**Checkpoint**: Users can browse full change history on the workflow detail page without leaving the page — User Story 2 is independently complete (US1 is a data prerequisite but US2's own surface is fully testable once revisions exist).

---

## Phase 5: User Story 3 — Jump to the conversation that caused a change (Priority: P2)

**Goal**: Chat-originated revisions offer a "View conversation" action that opens the originating chat session and scrolls to/highlights the triggering user message; API-originated revisions show no such link; broken links show a clear unavailable state.

**Independent Test**: Ask Ze in chat to change a step's failure policy; open Change History on the workflow page; click the revision's conversation link; verify navigation lands in chat at the originating session/message, scrolled and highlighted.

### Tests for User Story 3

- [X] T034 [P] [US3] Component test: "View conversation" action is shown only when `actor_source === "agent"` and hidden for `actor_source === "api"` (actor label only) in `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.test.tsx`
- [X] T035 [P] [US3] Test: `session-store`'s `selectSession` plus a new highlight target correctly sets the message to scroll-to/highlight, and clears/shows an "unavailable" state when the session or message no longer exists, in `apps/ze-web/src/entities/session/model/session-store.test.ts`

### Implementation for User Story 3

- [X] T036 [US3] Add a `highlightMessageId: string | null` field + `setHighlightMessage(id: string | null)` action to `apps/ze-web/src/entities/session/model/session-store.ts`
- [X] T037 [US3] In `apps/ze-web/src/entities/message/ui/ChatMessageList.tsx`, scroll to and visually highlight the message matching `highlightMessageId` when set (clear the highlight after the scroll/initial render or on next user interaction) (depends on T036)
- [X] T038 [US3] In `apps/ze-web/src/entities/message/ui/MessageBubble.tsx`, accept/apply a highlighted style variant (depends on T037)
- [X] T039 [US3] Add "View conversation" button to each agent-attributed revision row in `WorkflowDetailPage.tsx` (Phase 4, T033) that calls `useSession.getState().selectSession(actor_session_id)` + `setHighlightMessage(actor_user_message_id)`, then navigates to `/` (chat route); if `actor_session_id` is missing/the session fetch 404s, show an inline "conversation unavailable" state instead of navigating (depends on T033, T036)

**Checkpoint**: Agent-made edits are traceable back to the exact chat turn — User Story 3 is independently complete.

---

## Phase 6: User Story 4 — Connect historical runs to definition changes (Priority: P3)

**Goal**: The existing 107b "definition changed since this run" banner offers a path to the revisions that occurred after that run's start time.

**Independent Test**: Run a workflow, edit its steps, reopen the old run; from the definition-changed banner, follow a link to revisions after the run's start time and verify they're filtered/highlighted accordingly.

### Tests for User Story 4

- [X] T040 [P] [US4] Component test: `WorkflowDefinitionNotice` in `historical-edited-since` mode renders a link/action that filters the Change History list to revisions with `created_at > run.started_at` in `apps/ze-web/src/widgets/workflow-graph/ui/WorkflowDefinitionNotice.test.tsx`

### Implementation for User Story 4

- [X] T041 [US4] Add an optional `onViewRevisionsSince?: () => void` prop to `WorkflowDefinitionNotice` in `apps/ze-web/src/widgets/workflow-graph/ui/WorkflowDefinitionNotice.tsx`, rendered as a link/button only in `historical-edited-since` mode
- [X] T042 [US4] In `WorkflowDetailPage.tsx`, wire `onViewRevisionsSince` to scroll to the Change History section and apply a client-side filter (`revision.created_at > displayExecution.started_at`) sourced from the already-fetched `useWorkflowRevisionsQuery` data (depends on T033, T041)

**Checkpoint**: All four user stories are independently functional; the 107b/108 loop is closed.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final validation across all stories.

- [X] T043 [P] Run `make lint` and `make format` across touched Python packages (`ze-automation`, `ze-api`, `ze-core`, `ze-agents`)
- [X] T044 [P] Run `make test-automation`, `make test-api`, `make test-core`, `make test-agents`, and `make test-web`
- [X] T045 Execute all 7 scenarios in `specs/phases/108-workflow-revision-audit/quickstart.md` end-to-end against `make dev-full`
- [X] T046 Update spec.md `**Status**` field from `Draft` to `Implemented` and update the phase 108 row in the root `CLAUDE.md` phase table and `specs/README.md` index (Constitution I: "status field... updated in the same commit as the implementation")

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational only. Must land first — it is the sole producer of `workflow_revisions` rows that US2/US3/US4 read.
- **User Story 2 (Phase 4)**: Depends on Foundational; functionally needs US1's write path to have real data, but its own code (schemas, route, query hook, UI) can be built/tested against mocked/seeded revisions in parallel with US1's later tasks.
- **User Story 3 (Phase 5)**: Depends on US2's Change History UI (T033) existing to host the "View conversation" button, and on US1's actor-context columns being populated.
- **User Story 4 (Phase 6)**: Depends on US2's Change History UI (T033) and the existing 107b `WorkflowDefinitionNotice`.
- **Polish (Phase 7)**: Depends on all desired stories being complete.

### Recommended Order

Foundational → US1 (P1, MVP) → US2 (P2) → US3 (P2) → US4 (P3) → Polish. US2/US3/US4 are UI-layer and can be staffed in parallel once US1's store-level write path (T015–T017) lands, even before T018–T022 (actor-context plumbing) finish, since US2's own tests can seed revisions directly via the store in tests.

### Within Each User Story

- Tests written first (marked, per Constitution V, non-negotiable), then implementation.
- Store/backend before REST route before frontend query hook before UI.

---

## Parallel Example: User Story 1

```bash
# All US1 tests (different files) can run in parallel:
Task: "Test PostgresWorkflowStore.create writes created revision (T007)"
Task: "Test PostgresWorkflowStore.update_steps writes edited revision (T008)"
Task: "Test revision 1 is unchanged after revision 2 is written (T009)"
Task: "Test update_steps skips no-op revisions (T010)"
Task: "Test update_steps skips revisions on validation failure (T011)"
Task: "Test cascade delete removes revisions (T012)"
Task: "Test tools construct ActorContext from injected deps (T013)"
Task: "Test _merge_deps injects session_id/user_message_id (T014)"
```

## Parallel Example: Foundational

```bash
Task: "Add zc026 migration (T002)"
Task: "Add ActorSource/ActorContext/WorkflowRevision types (T003)"
Task: "Create revision_summary.py diff function (T004)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (migration, types, diff function — CRITICAL, blocks everything)
3. Complete Phase 3: User Story 1 — every create/edit is durably recorded with actor context
4. **STOP and VALIDATE**: run Scenario 1–4 and 6 of quickstart.md directly against `list_revisions`/the DB (no UI needed yet)
5. This alone satisfies the spec's stated failure mode ("automated edits are opaque and untrustworthy") even before any UI ships

### Incremental Delivery

1. Foundational + US1 → durable, attributable audit log exists (MVP)
2. + US2 → users can browse it on the workflow page
3. + US3 → users can jump back to the originating conversation
4. + US4 → historical runs link forward to the revisions that changed them since

### Notes

- [P] tasks touch different files and have no ordering dependency within their phase.
- Constitution VI requires the migration to be raw SQL, in the `ze-automation` package's own `zc` chain — T002 is on the critical path for every other backend task.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
