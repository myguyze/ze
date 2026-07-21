# Feature Specification: Workflow Revision Audit

**Feature Branch**: `108-workflow-revision-audit`

**Created**: 2026-07-14

**Status**: Implemented

**Input**: User description: "Workflow definition audit trail — append-only revision log on every workflow creation and step edit (agent, API), with actor context linkable back to the originating chat conversation, REST list endpoint, and change history on workflow detail page; links from 107b definition-changed banner."

## Clarifications

### Session 2026-07-15

- Q: When a workflow is deleted, what happens to its revision history? → A: Cascade-delete — revisions are removed with the workflow; no orphan audit rows.
- Q: When the user clicks "View conversation" on a revision, how precise should navigation be? → A: Open chat and scroll/highlight the user message that triggered the edit.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Every definition change is recorded (Priority: P1)

A user asks Ze to change a workflow step (e.g. set step 3's failure handling to continue when no news is found). Ze makes the edit successfully, but the user has no durable record of what changed, when, or why the current definition differs from an older run. Today they must infer history from chat or guess.

**Why this priority**: Without a persisted revision log, automated edits are opaque and untrustworthy — the exact failure mode that motivated this phase. Recording creation and every subsequent step edit is the foundation all other stories build on.

**Independent Test**: Create a workflow via the workflow agent, then edit one step's failure policy via chat. Fetch the workflow's revision history and verify two entries exist: one for creation (initial steps) and one for the edit (before/after steps, actor attributed to the chat session).

**Acceptance Scenarios**:

1. **Given** a new workflow is created (today, only via the workflow agent's `create_workflow` tool — there is no REST creation endpoint), **When** creation completes, **Then** revision 1 is recorded with change type `created`, the full initial step list as `steps_after`, empty `steps_before`, and actor context for how it was created.
2. **Given** an existing workflow, **When** its step list is replaced via agent tool or API, **Then** a new append-only revision is recorded with `steps_before` (prior definition) and `steps_after` (new definition).
3. **Given** a revision is written, **When** any later operation occurs, **Then** prior revision rows are never modified or deleted.
4. **Given** an edit originates from a chat turn where Ze called the step-edit tool, **When** the revision is recorded, **Then** actor context includes session id and the user message id needed to deep-link and scroll to that turn.
5. **Given** an edit originates from a direct API call, **When** the revision is recorded, **Then** actor source is attributed as API (no chat deep link).

---

### User Story 2 - Review change history on the workflow page (Priority: P2)

After Ze or the user changes a workflow over time, the user opens the workflow detail page and wants a readable timeline of what changed — not raw JSON dumps — so they can understand how the definition evolved and why historical runs (pinned by 107b snapshots) may look different from the current graph.

**Why this priority**: The revision log only delivers value if the user can browse it without leaving the workflow context. This pairs directly with the 107b "definition changed since this run" banner.

**Independent Test**: Edit a workflow twice, open its detail page, expand "Change history", and verify entries appear newest-first with human-readable summaries (e.g. "Step s1: on_failure fail → continue") and timestamps.

**Acceptance Scenarios**:

1. **Given** a workflow with one or more revisions, **When** the user opens the workflow detail page, **Then** a "Change history" section lists revisions in reverse-chronological order.
2. **Given** a revision entry, **When** displayed in the list, **Then** it shows at minimum: revision number, timestamp, change type (created / edited), actor label (e.g. "Ze", "API"), and a short summary of what changed.
3. **Given** a revision entry, **When** the user expands it, **Then** they can inspect the full before and after step definitions.
4. **Given** a workflow with no revisions (legacy, pre-migration), **When** the user opens the detail page, **Then** the change history section shows an explicit empty/legacy state rather than failing silently.

---

### User Story 3 - Jump to the conversation that caused a change (Priority: P2)

When Ze edits a workflow in chat, the user wants to reopen the exact conversation turn that led to the change — to re-read the reasoning, undo mentally, or continue the thread — instead of hunting through message history.

**Why this priority**: Actor granularity was explicitly requested. Linking revisions back to chat is what makes agent-made edits auditable rather than just logged.

**Independent Test**: Ask Ze in chat to change a step's failure policy; after the edit, open change history on the workflow page and click the revision's conversation link; verify navigation lands in chat at the originating session/message context.

**Acceptance Scenarios**:

1. **Given** a revision whose actor source is the workflow agent in chat, **When** the user views that revision, **Then** a "View conversation" action is available.
2. **Given** the user clicks "View conversation", **When** navigation completes, **Then** the chat view opens on the originating session and scrolls to (and highlights) the user message that triggered the edit.
3. **Given** a revision attributed to API with no chat context, **When** the user views that revision, **Then** no conversation link is shown (actor label only).
4. **Given** the linked session or message no longer exists, **When** the user follows the link, **Then** a clear unavailable state is shown rather than a broken page.

---

### User Story 4 - Connect historical runs to definition changes (Priority: P3)

A user views an old workflow run whose graph differs from the current definition (107b "definition changed since this run" notice). They want to see which revision(s) happened after that run started, without manually comparing snapshots.

**Why this priority**: Closes the loop between per-run snapshots (107b) and cross-edit history (108). Lower priority because the banner + change history alone already unblock the Trump-workflow scenario.

**Independent Test**: Run a workflow, edit its steps, reopen the old run. From the definition-changed banner, follow a link to revisions that occurred after the run's start time.

**Acceptance Scenarios**:

1. **Given** a historical run where the pinned snapshot differs from the current definition, **When** the 107b definition-changed banner is shown, **Then** it offers a path to view revisions that occurred after that run started.
2. **Given** the user follows that path, **When** the change history is shown, **Then** revisions are filtered or highlighted to those after the run's start time.

---

### Edge Cases

- What happens when a step edit is rejected by validation? No revision row is written.
- What happens when creation fails partway? No revision row is written.
- What happens when the same steps are submitted unchanged? No revision row is written (no-op edits are not logged).
- How are workflows created before this phase handled? They have no revision history; UI shows a legacy empty state. Optional one-time backfill is out of scope.
- What about schedule-only changes via `update_workflow`? Out of scope for v1 — only step-definition changes and initial creation are audited.
- What if actor context (session/message) is missing due to a non-chat code path? Revision is still recorded with best-effort actor source; conversation link is omitted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST append a revision record when a new workflow is successfully created, capturing the full initial step list.
- **FR-002**: The system MUST append a revision record when a workflow's step list is successfully replaced, capturing `steps_before` and `steps_after`.
- **FR-003**: Revision records MUST be append-only; existing revisions MUST NOT be updated or deleted by any workflow operation.
- **FR-004**: Each revision MUST include a monotonically increasing revision number per workflow, a timestamp, and a change type (`created` or `edited`).
- **FR-005**: Each revision MUST record actor source as one of: `agent` (workflow agent in chat), `api` (REST or other direct API), or `system` (internal/bootstrap paths if any).
- **FR-006**: When actor source is `agent`, the revision MUST store actor context including session id and user message id sufficient to open chat and scroll/highlight the message that triggered the edit.
- **FR-007**: Each revision MUST include a human-readable summary of what changed (e.g. field-level deltas on steps such as `on_failure`, `task`, `verify`, branches).
- **FR-008**: The system MUST NOT write a revision when a create or step edit fails validation or is a no-op (identical steps).
- **FR-009**: The system MUST expose the revision history for a workflow to clients in reverse-chronological order with pagination.
- **FR-010**: The workflow detail page MUST show a "Change history" section listing revisions per FR-007 display rules.
- **FR-011**: Revisions with chat actor context MUST offer a "View conversation" action that navigates to chat, loads the originating session, and scrolls to the user message that triggered the edit.
- **FR-012**: When a historical run shows the 107b definition-changed banner, the UI MUST provide a path to revisions that occurred after that run's start time.
- **FR-013**: Step edits made by the existing workflow agent tool and REST step-update endpoint MUST both flow through the same revision-writing path (single audit hook).
- **FR-014**: When a workflow is deleted, its revision history MUST be cascade-deleted with it — no orphan revision rows remain.

### Key Entities

- **Workflow Revision**: An immutable record of one definition change. Attributes: workflow reference, revision number, change type (`created` | `edited`), timestamp, actor source, optional actor context (session id, message id, tool-call reference), steps before (empty on create), steps after, human-readable summary.
- **Actor Context**: Linkage metadata for chat-originated changes: session id and user message id (required when actor source is `agent`). Used for display and message-level deep-linking.
- **Change Summary**: A derived, human-readable description of the delta between before and after steps (which step ids changed, which fields).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of successful workflow creations and step-list replacements after this phase ships produce exactly one new revision row (verified for the agent tool creation path, and for both the agent tool and REST API step-replacement paths — there is no REST workflow-creation endpoint to verify against).
- **SC-002**: 0% of failed or no-op step edits produce a revision row.
- **SC-003**: A user can identify what changed in a workflow (creation or edit) within 30 seconds by reading the change history list without inspecting raw JSON.
- **SC-004**: For chat-originated edits where session/message context is captured, a user can reach the originating conversation in two clicks or fewer from the workflow detail page.
- **SC-005**: When viewing a historical run with a changed definition, a user can reach the post-run revision(s) in three clicks or fewer from the definition-changed banner.
- **SC-006**: Prior revision rows remain unchanged after subsequent edits (immutability verified by read-after-write test).

## Assumptions

- Phase 107 and 107b (`steps_snapshot` per run) are already shipped. This phase adds cross-edit history; it does not replace per-run snapshots.
- Single-user model: no per-user actor identity beyond source + optional chat linkage.
- Schedule-only updates remain out of scope; only step-definition changes and initial creation are audited.
- Rollback to a prior revision, side-by-side diff UI, and ze-web step *editing* UI are out of scope for v1 (read-only audit + chat/API write paths unchanged).
- Workflows created before this phase have no revision history unless explicitly backfilled in a future migration task (not required for v1).
- Revisions cascade-delete when a workflow is deleted, keeping storage bounded and avoiding orphan audit rows (confirmed in Clarifications).
- Chat deep-linking opens the originating session and scrolls to the user message that triggered the edit; requires capturing user message id in agent actor context at edit time.
- Workflow creation has exactly one call site today (the workflow agent's `create_workflow` tool) — there is no REST creation endpoint. "API" as an actor source therefore applies only to step-list replacement (`PATCH .../steps`) in this phase's verification; adding a REST creation endpoint is out of scope.

## Dependencies

- Phase 107: step editing via REST and `edit_workflow_steps` agent tool (write paths to hook).
- Phase 107b: `WorkflowDefinitionNotice` banner on workflow detail (integration point for Story 4).
- Existing chat page and message/session storage (deep-link target for Story 3).

## Out of Scope (Deferred)

- Rollback / restore workflow to revision N
- Auditing schedule-only changes
- Fancy visual diff (graph overlay, field-level highlight beyond text summary)
- ze-web inline step editing UI
- Backfilling revision 1 for pre-existing workflows
- Full workflow versioning with named branches or tags
