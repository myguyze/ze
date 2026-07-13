---

description: "Task list for Notification Center (105)"
---

# Tasks: Notification Center

**Input**: Design documents from `/specs/phases/105-notification-center/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included — constitution Principle V (Test Discipline) is non-negotiable for this project; every package/story below ships tests.

**Organization**: Tasks are grouped by user story (spec.md priorities P1/P2/P3) to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1 (see history), US2 (live delivery), US3 (act on / clean up)

## Path Conventions

Existing monorepo (see plan.md Project Structure): `core/ze-proactive/`, `core/ze-agents/`, `apps/ze-api/`, `apps/ze-web/`, plus job call sites in `plugins/*` and `core/ze-automation/`.

---

## Phase 1: Setup

**Purpose**: Confirm scaffolding needed before any schema/code changes; no new packages or dependencies are required (plan.md — feature is additive to existing packages).

- [ ] T001 Confirm `ze-proactive`'s Alembic `zpro` chain head matches `zpro001_push_log` in `core/ze-proactive/ze_proactive/migrations/versions/` so `zpro002_notifications.py` chains correctly

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared persistence, types, and DI wiring that every user story depends on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T002 Write migration `zpro002_notifications.py` in `core/ze-proactive/ze_proactive/migrations/versions/` creating the `notifications` table per data-model.md (columns, `(created_at DESC)` index, `(event_type, target_type, target_id, created_at)` index, partial `(read_at) WHERE read_at IS NULL` index)
- [ ] T003 [P] Add `NotificationRow`/`Notification` dataclass to `core/ze-proactive/ze_proactive/types.py` (new file) matching data-model.md's wire shape
- [ ] T004 [P] Add `event_type`, `title`, `target_type`, `target_id` optional fields to the `Notification` dataclass in `core/ze-agents/ze_agents/interface/types.py` (keep existing `content`/`format`/`urgency`/`actions` fields for backward compatibility with unstructured `push(str)` calls)
- [ ] T005 Implement `NotificationStore` in `core/ze-proactive/ze_proactive/notification_store.py`: `create()`, `list_page(cursor, limit, unread_only, mark_read)`, `unread_count()`, `mark_read(id)`, `mark_all_read()`, `exists_recent(event_type, target_type, target_id, hours)` (dedup query, research R3) — asyncpg-backed, depends on T002/T003
- [ ] T005a [P] Add `NotificationStore.prune_read_older_than(days: int = 90)` to `core/ze-proactive/ze_proactive/notification_store.py` (FR-015) — deletes rows where `read_at IS NOT NULL AND read_at < now() - days`; unread rows are never touched — depends on T005
- [ ] T006 Extend `ProactiveNotifier` in `core/ze-proactive/ze_proactive/notifier.py` with a `notify(event_type, title, body, *, source, target_type=None, target_id=None, hours=None)` method that: checks `NotificationStore.exists_recent` when `hours` is given, writes via `NotificationStore.create`, then calls `self._interface.push(...)` with the structured `Notification` (T004) for existing chat/ntfy delivery — depends on T004, T005
- [ ] T006a Confirm which `PushLogStore` is actually injected into proactive jobs today by tracing `apps/ze-api/ze_api/container.py`'s DI wiring. If jobs resolve `core/ze-core/ze_core/proactive/push_log_store.py` (the stale duplicate — missing `count_sent_within_hours`, still imported by `ze_core/__init__.py` and `plugins/ze-calendar/tests/jobs/test_reminders.py`) instead of `core/ze-proactive/ze_proactive/push_log_store.py`, either (a) repoint that DI wiring to the `ze-proactive` copy, or (b) if the `ze_core` copy is confirmed dead code from the phase-48 split, delete it and its lingering import/test references in a small standalone cleanup commit — do not fold silent removal into T007
- [ ] T007 Wire `NotificationStore` into DI: add to `plugin_deps`/constructor wiring in `apps/ze-api/ze_api/container.py` so `ProactiveNotifier` and the new REST routes can resolve it — depends on T005, T006a
- [ ] T008 [P] Write unit tests for `NotificationStore` (mocked asyncpg pool) in `core/ze-proactive/tests/test_notification_store.py`, covering pagination, `unread_count`, `mark_read`/`mark_all_read`, and the `exists_recent` dedup scoping from research R3 (same event_type+different target must NOT dedup against each other) — depends on T005
- [ ] T009 [P] Write unit tests for `ProactiveNotifier.notify()` in `core/ze-proactive/tests/test_notifier.py` (mocked `NotificationStore` + `AppInterface`) covering the dedup-skip path and the persist-then-deliver path — depends on T006

**Checkpoint**: Foundation ready — `notifications` table, store, and structured notify path all exist and are tested. User stories can now proceed.

---

## Phase 3: User Story 1 - See what happened while I was away (Priority: P1) 🎯 MVP

**Goal**: Persisted, paginated notification history with an unread badge on the bell, populated by real proactive events.

**Independent Test**: Trigger a proactive job while disconnected, reopen the web app, click the bell — the event appears with title/body/timestamp/source and the badge showed the correct unread count beforehand.

### Tests for User Story 1

- [ ] T010 [P] [US1] Contract test for `GET /api/v0/notifications` and `GET /api/v0/notifications/unread-count` in `apps/ze-api/tests/api/routes/test_notifications.py` (pagination, `unread_only`, response shape per contracts/rest-api.md)
- [ ] T011 [P] [US1] Component test for `NotificationBell` badge + list rendering in `apps/ze-web/src/widgets/notification-bell/ui/NotificationBell.test.tsx`

### Implementation for User Story 1

- [ ] T012 [P] [US1] Add `NotificationItem`, `NotificationListResponse`, `UnreadCountResponse` Pydantic models to `apps/ze-api/ze_api/api/schemas.py`
- [ ] T013 [US1] Implement `GET /api/v0/notifications` and `GET /api/v0/notifications/unread-count` in new `apps/ze-api/ze_api/api/routes/notifications.py` (cursor pagination, `unread_only` filter; `mark_read` param wired but exercised in US3), register router in `apps/ze-api/ze_api/api/__init__.py` — depends on T007, T012
- [ ] T014 [US1] Adopt `ProactiveNotifier.notify()` (T006) in `plugins/ze-personal/ze_personal/jobs/briefing.py` (`event_type="morning_brief"`, `source="personal"`, no target) replacing the current plain `notifier.push(str)` call
- [ ] T015 [P] [US1] Adopt `notify()` in `plugins/ze-personal/ze_personal/jobs/insights.py` (`event_type="insight_digest"`, `source="personal"`)
- [ ] T016 [P] [US1] Adopt `notify()` in `plugins/ze-calendar/ze_calendar/jobs/calendar_reminder.py` (`event_type="calendar_reminder"`, `source="calendar"`, `target_type="reminder"`, `target_id=<reminder id>`)
- [ ] T017 [P] [US1] Adopt `notify()` in `core/ze-automation/ze_automation/jobs/stuck_goals.py` (`event_type="stuck_goal"`, `source="goals"`, `target_type="goal"`, `target_id=<goal id>`, `hours=` matching its existing rate-limit window per research R3)
- [ ] T018 [P] [US1] Adopt `notify()` in `core/ze-automation/ze_automation/jobs/cost_anomaly.py` (`event_type="cost_anomaly"`, `source="accountability"`)
- [ ] T019 [P] [US1] Adopt `notify()` in `core/ze-automation/ze_automation/jobs/goal_suggestion.py` (`event_type="goal_suggestion"`, `source="goals"`, `target_type="goal_suggestion"`, `target_id=<suggestion id>`)
- [ ] T020 [P] [US1] Adopt `notify()` in `core/ze-automation/ze_automation/jobs/accountability.py` (`event_type="accountability_narrative"`, `source="accountability"`)
- [ ] T021a [US1] Adopt `notify()` at the goal-gate-reached call site in `core/ze-automation/ze_automation/agents/goals/agent.py` (or `tools.py` — both already import `ProactiveNotifier`; confirm the exact gate-reached branch) with `event_type="goal_gate"`, `source="goals"`, `target_type="goal"`, `target_id=<goal id>`
- [ ] T021b [US1] Add a **new** live `notify()` call for workflow failures — today `workflow_failure` is only ever written to `push_log` (see `ze_automation/bootstrap.py`, `ze_automation/rest.py`, `accountability/summarizer.py`), there is no existing `ProactiveNotifier` call for it anywhere. Add the call at the point the workflow scheduler/executor currently calls `push_log.log("workflow_failure:...")`, with `event_type="workflow_failure"`, `source="workflows"`, `target_type="workflow_run"`, `target_id=<run id>` — requires injecting `ProactiveNotifier` into that executor/job if not already present
- [ ] T022 [P] [US1] Create `apps/ze-web/src/entities/notification/` — `api/useNotificationsQuery.ts`, `api/useUnreadCountQuery.ts`, `index.ts` (types re-exported from `@ze/client`)
- [ ] T023 [US1] Create `apps/ze-web/src/widgets/notification-bell/ui/NotificationBell.tsx` — badge showing unread count, dropdown/panel rendering the paginated list with infinite scroll — depends on T022
- [ ] T024 [US1] Replace the static `<Bell>` button in `apps/ze-web/src/shared/ui/layout/TopBar.tsx` with `NotificationBell` — depends on T023
- [ ] T025 [US1] Regenerate `@ze/client` SDK types from the new OpenAPI routes (per phase 72's codegen pattern) so `NotificationItem` etc. are typed in the frontend — depends on T013

**Checkpoint**: User Story 1 fully functional — bell shows real history and unread count, independently of live updates or read-tracking.

---

## Phase 4: User Story 2 - Notifications appear live while I'm using the app (Priority: P2)

**Goal**: New proactive events appear in the bell within seconds while connected, without a page refresh.

**Independent Test**: With the app open and connected, trigger an event server-side; unread count and list update within a few seconds without reload.

### Tests for User Story 2

- [ ] T026 [P] [US2] Test that `NativeAppInterface.push()`/`notify()` path emits a `"notification"` WS frame (mocked `ConnectionManager`) in `apps/ze-api/tests/interface/test_native.py`
- [ ] T027 [P] [US2] Test that the WS frame dispatcher in `apps/ze-web/src/features/invalidate-on-ws-refresh/ui/RefreshHandler.tsx` updates the notifications query cache and unread count on a `"notification"` frame, in `apps/ze-web/src/features/invalidate-on-ws-refresh/ui/RefreshHandler.test.tsx`

### Implementation for User Story 2

- [ ] T028 [US2] Modify `NativeAppInterface.push()` in `apps/ze-api/ze_api/interface/native.py` to send a `{"type": "notification", ...}` frame via `ConnectionManager.send_frame` (per contracts/ws-frame.md) whenever a structured (T004) notification is pushed, in addition to existing chat/ntfy delivery — depends on T028's test T026 failing first, and on Foundational T006
- [ ] T029 [P] [US2] Document the `"notification"` frame type in `apps/ze-api/ze_api/api/websocket/ws_schema.py`
- [ ] T030 [US2] Extend `apps/ze-web/src/features/invalidate-on-ws-refresh/ui/RefreshHandler.tsx` to handle `type === "notification"`: prepend to the cached notifications list and increment cached unread count — depends on T022

**Checkpoint**: User Stories 1 AND 2 both work — live delivery layers on top of the working history without changing it.

---

## Phase 5: User Story 3 - Act on and clean up notifications (Priority: P3)

**Goal**: Mark-as-read (auto on view + explicit "mark all"), deep-link navigation, graceful handling of deleted link targets.

**Independent Test**: Open the panel (items auto-mark read), click a deep-linked item (navigates + marks read), click one whose target is gone (shows "no longer available"), use "mark all read" (badge → 0).

### Tests for User Story 3

- [ ] T031 [P] [US3] Contract test for `POST /api/v0/notifications/{id}/read` and `POST /api/v0/notifications/read-all` in `apps/ze-api/tests/api/routes/test_notifications.py`
- [ ] T032 [P] [US3] Test `GET /api/v0/notifications?mark_read=true` marks the returned page read in `apps/ze-api/tests/api/routes/test_notifications.py`
- [ ] T033 [P] [US3] Frontend test: opening `NotificationBell` triggers the `mark_read=true` fetch and clears visible unread state, in `apps/ze-web/src/widgets/notification-bell/ui/NotificationBell.test.tsx`

### Implementation for User Story 3

- [ ] T034 [US3] Implement `POST /api/v0/notifications/{id}/read` and `POST /api/v0/notifications/read-all` in `apps/ze-api/ze_api/api/routes/notifications.py` — depends on T013
- [ ] T035 [US3] Wire `mark_read=true` behavior into the existing `GET /api/v0/notifications` handler (atomically mark returned page read) — depends on T013
- [ ] T036 [P] [US3] Add `useMarkReadMutation.ts` and `useMarkAllReadMutation.ts` to `apps/ze-web/src/entities/notification/api/` — depends on T022
- [ ] T037 [US3] Have `NotificationBell`'s panel-open fetch call `GET /api/v0/notifications?mark_read=true` (auto-mark-on-view per Clarification 2026-07-13) and wire the explicit "mark all read" action to `useMarkAllReadMutation` — depends on T023, T036
- [ ] T038 [US3] Add click-to-navigate on deep-linked notifications (route by `target_type`/`target_id` to the relevant goal/workflow/reminder page) in `apps/ze-web/src/widgets/notification-bell/ui/NotificationBell.tsx`, with a "no longer available" fallback state when the target 404s (FR-009) — depends on T023

**Checkpoint**: All three user stories independently functional; full spec (FR-001–FR-015) covered.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T038a [P] Wire `NotificationStore.prune_read_older_than(90)` into a daily proactive job (new `core/ze-proactive/ze_proactive/jobs/prune_notifications.py` `@proactive_job`, or a hook on an existing daily job) so FR-015 retention actually runs — depends on T005a
- [ ] T038b [P] Unit test for `prune_read_older_than` (mocked pool: unread rows survive regardless of age, read rows older than the cutoff are deleted, read rows within the window survive) in `core/ze-proactive/tests/test_notification_store.py` — depends on T005a
- [ ] T039 [P] Update `specs/README.md` phase index row for 105 and flip `spec.md` status to `Implemented` in the same commit as the last implementation task, per constitution Principle I
- [ ] T040 [P] Add the `notifications` table to the migration-ownership table in `CLAUDE.md` (`ze-proactive` row, `zpro` prefix)
- [ ] T041 Run `quickstart.md` scenarios 1–5 end-to-end against `make dev-full`
- [ ] T042 `make lint` and `make test-proactive`, `make test`, `make test-web` all green

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories (table, store, structured `notify()` must exist before any job or route can use them).
- **User Story 1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **User Story 2 (Phase 4)**: Depends on Foundational; reuses US1's `entities/notification` query hooks (T022) and its own WS frame is additive — does not modify US1's REST contract.
- **User Story 3 (Phase 5)**: Depends on Foundational and on US1's route file/entity scaffolding existing (T013, T022) since it adds handlers/hooks alongside them, but does not require US2 to be done.
- **Polish (Phase 6)**: After all desired stories are complete.

### Parallel Opportunities

- T003/T004 (dataclass additions in two different packages) can run in parallel.
- T008/T009 (foundational tests) can run in parallel once T005/T006 land.
- T014–T020 (job adoption across 7 different plugin/automation files) are almost entirely parallel — different files, same `notify()` API from T006.
- T022 and T012 can run in parallel (frontend entity scaffolding vs backend schemas).
- T026/T027 (US2 tests) in parallel; T031/T032/T033 (US3 tests) in parallel.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — table, store, structured `notify()`, DI wiring.
2. Complete Phase 3 (US1) — real jobs emit structured notifications, REST list + unread-count exist, bell shows real history.
3. **STOP and VALIDATE**: run quickstart.md Scenario 1 and 3.
4. This alone already satisfies SC-001, SC-003, and half of the original ask (the bell is no longer decorative).

### Incremental Delivery

1. Foundational → US1 (MVP, history + badge) → US2 (live delivery) → US3 (read state + deep links) → Polish.
2. Each story is independently demoable per its Independent Test above.
