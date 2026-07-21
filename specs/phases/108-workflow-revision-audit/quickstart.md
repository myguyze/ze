# Quickstart: Validating Workflow Revision Audit

## Prerequisites

```bash
make db-up
make migrate        # applies zc026_workflow_revisions.py
make dev-full        # backend :8000 + web :5173
```

## Scenario 1 — creation is recorded (Story 1, Acceptance Scenario 1)

1. In the web chat, ask Ze: *"Create a workflow called 'News Digest' that fetches
   today's headlines every morning at 8am."*
2. Once Ze confirms creation, call:
   ```bash
   curl -s -H "Authorization: Bearer $ZE_API_KEY" \
     "http://localhost:8000/api/v0/workflows/$WORKFLOW_ID/revisions" | jq
   ```
3. **Expected**: exactly one revision, `revision_number: 1`, `change_type: "created"`,
   `steps_before: []`, `steps_after` matching the planned steps, `actor_source:
   "agent"` with a non-null `actor_session_id` and `actor_user_message_id`.

## Scenario 2 — step edit is recorded with a diff summary (Story 1 AS 2, Story 2)

1. In the same chat thread, ask: *"Change the News Digest workflow so if no news is
   found it continues instead of failing."*
2. Re-fetch `GET /workflows/{id}/revisions`.
3. **Expected**: a second revision, `revision_number: 2`, `change_type: "edited"`,
   `steps_before` equal to revision 1's `steps_after`, `summary` containing an
   `on_failure` delta phrase (e.g. `"Step s1: on_failure fail → continue"`).
4. Open the workflow detail page in the browser (`/workflows/{id}`), expand "Change
   History" — verify two entries, newest first, human-readable, with a "View
   conversation" link on both.

## Scenario 3 — no-op edit produces no revision (FR-008, Edge Cases)

1. Call `PATCH /api/v0/workflows/{id}/steps` with the *current* step list unchanged
   (fetch via `GET /workflows/{id}` first, resubmit as-is).
2. **Expected**: `GET /workflows/{id}/revisions` still shows only 2 revisions (no new
   row).

## Scenario 4 — API-originated edit has no chat link (Story 1 AS 5, Story 3 AS 3)

1. Repeat the `PATCH /{id}/steps` call from Scenario 3 but with an actual step change
   (e.g. flip `on_failure` back).
2. **Expected**: new revision has `actor_source: "api"`, `actor_session_id: null`,
   `actor_user_message_id: null`. On the detail page, this revision shows no "View
   conversation" action — actor label only ("API").

## Scenario 5 — "View conversation" navigates and highlights (Story 3 AS 1-2)

1. On the detail page, click "View conversation" on the agent-originated revision from
   Scenario 2.
2. **Expected**: navigates to the chat view, opens the originating session, scrolls to
   and highlights the user message that triggered the edit ("Change the News Digest
   workflow so if no news is found it continues instead of failing").

## Scenario 6 — cascade delete (clarification, FR-014)

1. Delete the workflow (`delete_workflow` tool or equivalent).
2. Query the DB directly:
   ```sql
   SELECT count(*) FROM workflow_revisions WHERE workflow_id = '<id>';
   ```
3. **Expected**: `0` — no orphan rows.

## Scenario 7 — legacy workflow with no revisions (Story 2 AS 4)

1. Find or create a workflow whose `workflows` row predates this phase (or, in a fresh
   DB, temporarily insert a `workflows` row directly via SQL bypassing the store to
   simulate a legacy row with zero revisions).
2. Open its detail page.
3. **Expected**: "Change History" section shows an explicit empty/legacy state, not a
   blank area or an error.

## Automated coverage (see tasks.md for the full breakdown)

- `core/ze-automation/tests/workflow/test_postgres_revisions.py` — revision write on
  create/update, no-op skip, cascade delete, revision numbering (mocked asyncpg pool).
- `core/ze-automation/tests/workflow/test_revision_summary.py` — diff summary
  generation for add/remove/field-change/create cases.
- `apps/ze-api/tests/api/routes/test_workflows_revisions.py` — `GET
  .../revisions` pagination, 404, response shape.
- `apps/ze-web/src/pages/workflow-detail/ui/WorkflowDetailPage.test.tsx` — Change
  History section renders, empty/legacy state, "View conversation" visibility rules.
