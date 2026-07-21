# Phase 0 Research: Workflow Revision Audit

## 1. Where does the revision write hook attach?

**Decision**: Write the revision row inside `PostgresWorkflowStore.create()` and
`.update_steps()`, on the same `conn` used for the `INSERT`/`UPDATE`, wrapped in an
explicit `conn.transaction()`.

**Rationale**: `update_steps` (`core/ze-automation/ze_automation/workflow/postgres.py:220-239`)
already validates steps and checks workflow existence before writing — the natural
place to also compute the diff and insert the revision row. Both write paths
(`edit_workflow_steps` agent tool and `PATCH /{workflow_id}/steps` REST route) call
`store.update_steps()` today, and `create_workflow` tool + any future REST create both
call `store.create()`. Hooking the store methods (not the callers) satisfies FR-013
("single audit hook") for free — no caller needs to know a revision exists.

**Alternatives considered**:
- *Hook at the REST/tool call sites*: rejected — would require duplicating the hook
  in `ze_automation/rest.py::update_workflow_steps` and
  `agents/workflow/tools.py::edit_workflow_steps`, violating "single audit hook."
- *Separate `WorkflowRevisionWriter` service called after the store method returns*:
  rejected — breaks atomicity (FR-008's "no revision on failure" and "no revision on
  no-op" are easiest to guarantee when the diff check and the write happen inside the
  same transaction as the mutation, using the row already fetched for the `UPDATE`).

## 2. How to compute "no-op" and the before/after diff

**Decision**: Inside `update_steps`, after fetching the current row (already done at
`postgres.py:224-227` to check existence), compare the *current* `steps` JSONB against
the incoming serialized steps (`[_step_to_dict(s) for s in steps]`) before running the
`UPDATE`. If equal, skip both the `UPDATE`'s "changed" bookkeeping is moot (still safe
to re-run `UPDATE ... SET steps = ...` harmlessly) but skip the revision insert
entirely — FR-008 only requires no *revision row*, not that the UPDATE be skipped.
A pure Python `==` on the two `list[dict]` structures (after `_step_to_dict`
normalization) is sufficient; no need for a DB-side comparison.

**Rationale**: Reuses the exact serialization (`_step_to_dict`) already used for the
write, so "identical steps" means byte-identical JSON, not a fuzzy diff — matches
spec's Edge Cases ("same steps submitted unchanged").

**Alternatives considered**: Hashing steps and storing a `content_hash` column for
future no-op checks — rejected as unnecessary; a full struct comparison is cheap at
this scale (single workflow, single edit) and avoids a schema column with no other use.

## 3. Human-readable change summary generation (FR-007)

**Decision**: New pure function `build_change_summary(before: list[WorkflowStep],
after: list[WorkflowStep]) -> str` in a new
`core/ze-automation/ze_automation/workflow/revision_summary.py`. Diff by step `id`:
- Steps present in `after` but not `before` → `"Step {id} added"`.
- Steps in `before` but not `after` → `"Step {id} removed"`.
- Steps in both with field-level differences → one clause per changed field, e.g.
  `"Step s3: on_failure fail → continue"`, matching the exact phrasing in the spec's
  Independent Test for Story 2. Fields compared: `task`, `agent_hint`, `verify`,
  `intent`, `branches`, `default_next`, `on_failure`.
- For `change type = created`: summary is `"Workflow created with N step(s)"`.
- Join multiple clauses with `"; "`. Truncate no further — this is a summary line, not
  a paragraph; full before/after remain inspectable via the detail expansion (FR-007,
  Story 2 Acceptance Scenario 3).

**Rationale**: Deterministic, no LLM call needed (keeps Constitution Principle VII
satisfied — no new LLM gateway usage), computed once at write time and stored
(`summary` column) rather than recomputed on every read.

**Alternatives considered**: LLM-generated summary — rejected as overkill for a
structured diff over a small, well-typed step schema; adds latency and cost to every
edit for no clarity gain over field-level deltas.

## 4. Actor context threading (session id + user message id)

**Decision**: Extend the existing `config["configurable"]` → `AgentContext` →
`agentic_loop` deps chain, reusing the `AgentContext.extensions: dict[str, str | int |
float | bool | None]` field already designed for exactly this ("must hold only
msgpack-serializable primitives"):

1. `apps/ze-api/ze_api/api/websocket/turns.py::handle_message` — after `user_msg =
   Message(id=uuid4(), ...)` is constructed (line ~56), add
   `config_extra["user_message_id"] = str(user_msg.id)`.
2. `core/ze-core/ze_core/orchestration/nodes/context.py::fetch_context` — read
   `config["configurable"].get("user_message_id")` and set
   `agent_context.extensions["user_message_id"] = user_message_id` when present (no
   new dataclass field needed on `AgentContext`; `session_id` already exists as a
   first-class field).
3. `core/ze-automation/ze_automation/agents/workflow/agent.py::WorkflowManagerAgent.run`
   — add `"session_id": ctx.session_id, "user_message_id":
   ctx.extensions.get("user_message_id")` to the `deps` dict passed to
   `agentic_loop(...)`.
4. `core/ze-automation/ze_automation/agents/workflow/tools.py::edit_workflow_steps` and
   `create_workflow` — add `session_id: str | None = None, user_message_id: str | None
   = None` parameters. `_merge_deps` (`ze_agents/base_agent.py:471-484`) auto-injects
   them from `deps` because they're not in the LLM-visible schema (the LLM never
   supplies them) and are present in `deps` by name — the same mechanism already used
   for `store`/`planner`/`scheduler`.
5. Tools construct an `ActorContext(source="agent", session_id=session_id,
   user_message_id=user_message_id)` and pass it to `store.create(...)` /
   `store.update_steps(..., actor=actor_context)`.
6. `PATCH /{workflow_id}/steps` REST route passes `ActorContext(source="api")` (no
   session/message) — FR-005, Acceptance Scenario 5.

**Rationale**: Zero new plumbing primitives — `extensions` was already built to carry
exactly this kind of msgpack-safe scalar without touching the checkpoint serde tests
("never checkpoint identity_builder/abort_token/token_sink" callables are the only
banned fields; plain strings in `extensions` are fine and already checkpointed today).
`_merge_deps`'s signature-inspection injection means no LLM schema change either — the
LLM never sees `session_id`/`user_message_id` as tool parameters it must fill in.

**Alternatives considered**: Adding `user_message_id: str | None` as a first-class
`AgentContext` field — rejected as unnecessary churn (would touch the checkpoint serde
allowlist and every `AgentContext(...)` construction site) when `extensions` already
exists for this purpose.

## 5. Revision table schema & migration numbering

**Decision**: `zc026_workflow_revisions.py`, `down_revision = "zc025"` (continues the
`ze-automation` package's `zc` chain, per `docs/…` migration-ownership table — no
`depends_on` needed since it only references `workflows.id` which already exists in
this same chain).

```sql
CREATE TABLE workflow_revisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    revision_number INT NOT NULL,
    change_type TEXT NOT NULL CHECK (change_type IN ('created', 'edited')),
    steps_before JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps_after JSONB NOT NULL,
    summary TEXT NOT NULL,
    actor_source TEXT NOT NULL CHECK (actor_source IN ('agent', 'api', 'system')),
    actor_session_id TEXT,
    actor_user_message_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX workflow_revisions_workflow_rev_idx
    ON workflow_revisions (workflow_id, revision_number);
CREATE INDEX workflow_revisions_workflow_created_idx
    ON workflow_revisions (workflow_id, created_at DESC);
```

**Rationale**: `ON DELETE CASCADE` directly satisfies FR-014/clarification 1 at the DB
level — no application-code cleanup needed on `store.delete()`. `revision_number` is
computed as `COALESCE(MAX(revision_number), 0) + 1` inside the same transaction as the
insert (`SELECT ... FOR UPDATE` not needed — single-user, single-writer-per-workflow
in practice, and a unique index catches any race rather than silently duplicating).
`actor_session_id`/`actor_user_message_id` are plain columns with **no FK** — `sessions`
and `messages` tables live in `ze-core`'s separate migration chain
(`core/ze-core/ze_core/migrations/versions/zc016_messages.py`,
`zc018_sessions.py`), and cross-chain FKs aren't used elsewhere in this codebase
(`accountability_anomalies.session_id TEXT`, no FK, is the existing precedent).
`steps_before`/`steps_after` are stored as JSONB (not normalized) to reuse
`_step_to_dict`/`_step_from_dict` unchanged and to keep each revision self-contained
and immutable even if `WorkflowStep`'s shape evolves later — matches how
`workflow_executions.steps_snapshot` (107b) already stores steps as JSONB for the same
reason.

**Alternatives considered**: `BIGSERIAL` primary key like `accountability_anomalies` —
rejected in favor of `UUID` to match the sibling `workflows`/`workflow_executions`
tables' PK style and to give the REST API a non-guessable, non-sequential external id
for individual revisions (`GET /workflows/{id}/revisions/{revision_id}` is not in v1
scope, but UUID keeps the door open cheaply).

## 6. List endpoint pagination shape

**Decision**: Offset-based, mirroring `GET /goals/{goal_id}/traces`
(`apps/ze-api/ze_api/api/routes/goals.py:118-159`): `GET
/workflows/{workflow_id}/revisions?limit=&offset=`, `limit: int = Query(default=20,
ge=1, le=100)`, `offset: int = Query(default=0, ge=0)`, ordered
`revision_number DESC` (equivalent to `created_at DESC` given monotonic numbering).
Store method: `list_revisions(workflow_id, limit=20, offset=0) -> list[WorkflowRevision]`.

**Rationale**: Per-workflow revision volume is small and bounded (tens of edits, not
an unbounded global feed), so cursor pagination (the `sessions` precedent) is
unnecessary complexity — `goal_execution_traces` is the closer analog (bounded,
per-entity, append-only log) and already established this offset convention in the
same package.

**Alternatives considered**: Cursor-based (`before: datetime`) like `GET /sessions` —
rejected, reserved for genuinely unbounded, cross-entity feeds.

## 7. Change-history UI placement

**Decision**: A third `SectionPanel` titled "Change History" in
`WorkflowDetailPage.tsx`'s existing 3-column grid (alongside "Steps" and "Run
History", `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.tsx:161-227`),
below "Run History" in the right column. Each row: revision number, relative
timestamp, change-type badge, actor label ("Ze" for `agent`, "API" for `api`), one-line
summary; expandable to show full before/after step JSON (reuse the existing
`WorkflowGraph`/step-list rendering primitives where practical); "View conversation"
button when `actor_source === "agent"` and message id present, navigating to
`/chat/:sessionId?highlight=:messageId` (exact route TBD in data-model/contracts —
chat page must support a highlight/scroll-to param; verify during implementation
whether this param already exists).

**Rationale**: Matches the FSD widget/entity pattern already used for
`WorkflowExecutionsList` (parallel structure: new list fed by a new
`useWorkflowRevisionsQuery` entity hook, rendered by a new widget or inline component
in the page). Keeps Story 2 and Story 3 UI changes localized to one page.

**Alternatives considered**: A separate `/workflows/:id/history` sub-page — rejected,
spec explicitly asks for change history "without leaving the workflow context"
(Story 2 rationale).

## 8. 107b banner → post-run revisions link (Story 4)

**Decision**: Extend `WorkflowDefinitionNotice` (`apps/ze-web/src/widgets/workflow-graph/ui/WorkflowDefinitionNotice.tsx`)
so that when `mode === "historical-edited-since"`, it renders a link that scrolls to
and filters the on-page Change History section to revisions with
`created_at > run.started_at` — no new route or endpoint; filtering happens client-side
against the already-fetched revisions list (or a `since` query param on the same list
endpoint if the revision count could be large — deferred to implementation, default to
client-side filtering given expected volume per research item 6).

**Rationale**: Keeps Story 4 (P3, lowest priority) cheap — reuses data already loaded
for Story 2 rather than introducing a new endpoint, satisfying SC-005 (three clicks or
fewer) trivially since it's an in-page scroll+filter.

**Alternatives considered**: A dedicated `?since=<timestamp>` query param on the list
endpoint — kept as a fallback noted above if client-side filtering proves insufficient
once real revision volumes are observed; not required for v1 given Assumption
"single-user, low edit frequency."
