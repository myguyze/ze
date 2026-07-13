# Implementation Plan: Notification Center

**Branch**: `105-notification-center` | **Date**: 2026-07-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/phases/105-notification-center/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

Wire the decorative Bell in the web app's top bar into a real, persisted notification feed. Every proactive job already funnels through the single `ProactiveNotifier` → `AppInterface.push()` call path (research R1); this feature adds a structured `notifications` table owned by `ze-proactive`, a paginated REST surface with read/unread state, a live `notification` WebSocket frame, and a frontend notification panel replacing the static bell button — without disturbing the existing chat-message/ntfy delivery those jobs already get.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript / React 18 (Vite) for `ze-web`

**Primary Dependencies**: FastAPI, asyncpg, existing `ze-proactive`/`ze-agents`/`ze-sdk` packages; frontend: React Query, existing WS client plumbing, shadcn/ui components, Feature-Sliced Design layout

**Storage**: PostgreSQL — new `notifications` table in the `ze-proactive` package's `zpro` Alembic chain (continues from `zpro001_push_log`)

**Testing**: pytest (`make test-proactive`, `make test`) with mocked asyncpg pools; vitest (`make test-web`) for the frontend panel/hooks

**Target Platform**: Existing Ze deployment — FastAPI server + React SPA over WebSocket, no new platform surface

**Project Type**: Web application (existing backend + frontend monorepo, Option 2 structure)

**Performance Goals**: Live notification delivery visible within 5s of the server-side event (SC-002); list/unread-count queries backed by the indexes in data-model.md, no full-table scans

**Constraints**: Single-user model (no per-user scoping, per constitution II); no new external dependencies; must not alter existing `push_log` dedup semantics for current callers (research R3); confirmations/`ConfirmBar` and `NoticeBanner` remain untouched (FR-014, out of scope)

**Scale/Scope**: Single user, expected notification volume on the order of tens per day across all plugins; 90-day default retention for read items (FR-015)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| I. Spec-First Development | Spec exists at `specs/phases/105-notification-center/spec.md`, status will move to `Planned`/`Implemented` in the same commits as work lands | Pass |
| II. Single-User Model | No `user_id` column on `notifications`; single API key auth reused | Pass |
| III. Layered Package Architecture | `notifications` table + store live in `ze-proactive` (core, no domain knowledge — `target_type`/`target_id` are opaque strings, not FKs into any plugin's schema); REST routes live in `ze-api` (composition root); plugins keep calling the existing `ProactiveNotifier`, no plugin gains a new direct dependency | Pass |
| IV. Typed, Explicit Python | `Notification`/`NotificationRow` as dataclasses in `types.py`; Pydantic only in `ze_api/api/schemas.py` for the new response models; errors via typed `ZeError` subclasses | Pass |
| V. Test Discipline | Unit tests for `NotificationStore` (mocked asyncpg), REST routes, WS frame emission, and the frontend panel/hooks — planned in tasks phase | Pass (to verify at tasks/implement) |
| VI. Explicit Persistence | Hand-written raw-SQL Alembic migration `zpro002_notifications.py` in `ze-proactive`, continuing the `zpro` chain, no ORM | Pass |
| VII. One LLM Gateway, Local Embeddings | Feature has no LLM involvement | N/A |
| FSD (frontend) | New `entities/notification` (query/mutation hooks) + `widgets/notification-bell` (panel), imported into `shared/ui/layout/TopBar.tsx`; respects `pages → widgets → features → entities → shared` layering | Pass |

No violations requiring the Complexity Tracking table.

## Project Structure

### Documentation (this feature)

```text
specs/phases/105-notification-center/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── rest-api.md
│   └── ws-frame.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
core/ze-proactive/ze_proactive/
├── notification_store.py          # NEW — NotificationStore (asyncpg), dedup query (R3)
├── notifier.py                    # MODIFIED — ProactiveNotifier gains structured push (event_type/title/target)
├── migrations/versions/
│   └── zpro002_notifications.py   # NEW — notifications table, indexes
└── tests/
    └── test_notification_store.py # NEW

core/ze-agents/ze_agents/interface/
└── types.py                        # MODIFIED — Notification gains event_type/title/target_type/target_id fields

apps/ze-api/ze_api/
├── interface/native.py             # MODIFIED — NativeAppInterface.push() persists + emits WS "notification" frame
├── api/routes/
│   └── notifications.py            # NEW — GET list, GET unread-count, POST read, POST read-all
├── api/schemas.py                  # MODIFIED — NotificationItem, NotificationListResponse, UnreadCountResponse, MarkAllReadResponse
├── api/websocket/ws_schema.py      # MODIFIED — document "notification" frame type
├── container.py                    # MODIFIED — wire NotificationStore into DI (plugin_deps / ZeContainer)
└── tests/
    └── api/routes/test_notifications.py  # NEW

apps/ze-web/src/
├── entities/notification/
│   ├── api/useNotificationsQuery.ts        # NEW
│   ├── api/useUnreadCountQuery.ts          # NEW
│   ├── api/useMarkReadMutation.ts          # NEW
│   ├── api/useMarkAllReadMutation.ts       # NEW
│   └── index.ts                             # NEW
├── widgets/notification-bell/
│   └── ui/NotificationBell.tsx              # NEW — dropdown panel + badge
├── shared/ui/layout/TopBar.tsx              # MODIFIED — replace static bell button with NotificationBell
├── features/invalidate-on-ws-refresh/
│   └── ui/RefreshHandler.tsx                # MODIFIED — handle "notification" WS frame case
└── src/**/*.test.tsx                        # NEW tests for the above
```

**Structure Decision**: Existing monorepo layout (Option 2: backend `apps/ze-api` + frontend `apps/ze-web`, plus the `core/` package split already established). No new packages are created — the feature is additive to `ze-proactive` (core, table + store), `ze-agents` (core, shared `Notification` type), `ze-api` (composition root, routes + WS wiring), and `ze-web` (FSD entity + widget). This matches how every existing cross-cutting feature (e.g. trace panel, message trace) has been added in this codebase.

## Complexity Tracking

*No Constitution Check violations — table intentionally omitted.*
