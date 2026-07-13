# Quickstart: Notification Center

Validation scenarios proving the feature end-to-end. Assumes `make db-up`, `make migrate`, and `make dev-full` (backend + web on :5173) are running per `docs/testing.md`.

## Prerequisites

- `zpro002_notifications` migration applied (`make migrate`).
- Web app open and logged in at `http://localhost:5173`.

## Scenario 1 — History for a disconnected event (US1)

1. Close the web app tab (or otherwise disconnect the WebSocket).
2. Trigger a proactive job that emits a notification, e.g. run the stuck-goal job directly:
   ```bash
   make test-automation  # or invoke the job's run() via a scratch script / eval harness
   ```
   (Any job wired through `ProactiveNotifier` with structured fields works; workflow-failure is easiest to trigger by failing a scheduled workflow run.)
3. Reopen the web app, click the bell.
4. **Expected**: the event appears in the list with a title, body, timestamp, and source area; the bell showed a nonzero unread count before opening.

## Scenario 2 — Live delivery while connected (US2)

1. With the web app open and connected, trigger the same kind of event server-side.
2. **Expected**: within a few seconds, the bell's unread count increments and the new item appears at the top of the list without a page reload (verify via the `notification` WS frame in the browser's network/WS inspector).

## Scenario 3 — Dedup by event type + target (Clarification R3)

1. Trigger a stuck-goal alert for Goal A twice within the job's dedup window.
2. Trigger a stuck-goal alert for Goal B within the same window.
3. **Expected**: exactly one notification for Goal A, and a separate notification for Goal B — not deduped against each other.

## Scenario 4 — Read-on-view and deep link (US3)

1. With at least one unread notification present, open the bell panel.
2. **Expected**: the unread count drops to reflect the now-viewed items (auto-mark-read on open, Clarification 2026-07-13).
3. Click a notification with a deep link (e.g. to a goal).
4. **Expected**: navigation to that goal's page; item stays read.
5. Click a notification whose linked goal has since been deleted.
6. **Expected**: a clear "no longer available" message, not a broken page (FR-009).

## Scenario 5 — Mark all read

1. With several unread notifications present, use the "mark all read" action in the panel.
2. **Expected**: unread badge goes to 0 in one action (SC-006).
