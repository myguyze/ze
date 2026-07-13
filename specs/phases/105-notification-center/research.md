# Research: Notification Center

## R1 — How proactive events are actually delivered today

**Decision**: The bell will hook into the existing `ProactiveNotifier` → `AppInterface.push()` call path, not a new parallel path.

**Rationale**: Tracing the real call sites (e.g. `plugins/ze-personal/ze_personal/jobs/briefing.py`) shows every proactive job already funnels through the single injected `ProactiveNotifier` (`core/ze-proactive/ze_proactive/notifier.py`), which calls `AppInterface.push(Notification)`. `NativeAppInterface.push()` (`apps/ze-api/ze_api/interface/native.py`) currently: saves the content as an assistant `Message` (so when connected, the user sees it appear inline in chat) and, only when the WebSocket is disconnected, also sends it via ntfy. There is no ntfy-only path today — the spec's "currently only produces an ntfy push" was a simplification; the accurate baseline is "chat message when connected, ntfy push when not, with no structured/queryable record and no read state." This is actually a better integration point than building a second delivery path: every existing and future job that calls `notifier.push(...)` already exercises the one choke point (`NativeAppInterface.push`), which satisfies FR-013 (common mechanism for any plugin) for free.

**Alternatives considered**: A brand-new `notify()` call plugins would opt into separately — rejected because it requires touching every job's call site immediately and creates two parallel mental models ("push" vs "notify") for what is the same concept from the plugin author's point of view. Structured fields are instead added to the existing `Notification` type so jobs can adopt them incrementally.

## R2 — Where to persist notification records

**Decision**: New `notifications` table owned by `ze-proactive` (continues the `zpro` migration chain that already owns `push_log`).

**Rationale**: `ze-proactive` is the core package that already owns proactive-job plumbing (`push_log`, `ProactiveScheduler`, `ProactiveNotifier`) and has no domain knowledge — consistent with the constitution's layered architecture (core packages carry no domain knowledge; a notification record referencing "goal 123" is just an opaque `target_type`/`target_id` string pair, not a foreign key into goals). Evolving `push_log` in place was considered (per the spec's "or an evolution of it" note) but rejected: `push_log` is a write-mostly, unindexed-for-read dedup ledger used internally by jobs; overloading it with user-facing title/body/read-state fields and read-heavy pagination queries mixes two different access patterns on one table. A sibling table sharing the same package and migration chain gets the benefit (one owner, same dedup source data) without the coupling.

**Alternatives considered**: Owning the table in `ze-api` — rejected, `ze-api` owns no tables per the constitution. Owning it in `ze-notifications` (the ntfy wrapper) — rejected, that package is a thin external-service wrapper with no persistence today and no domain reason to gain a store.

## R3 — Dedup key granularity (Clarification: event type + target entity)

**Decision**: `notifications` carries `target_type`/`target_id` columns; a new `NotificationStore.exists_recent(event_type, target_type, target_id, hours)` query backs dedup, independent of `push_log`'s existing coarser `event_type`-only dedup.

**Rationale**: `push_log.was_sent_within_hours(event_type, hours)` has no target column — it was built for whole-category rate limiting ("don't send more than one morning briefing per 20h"), which is correct for briefing/digest-style events but wrong for per-entity alerts (a stuck-goal alert for Goal A must not suppress one for Goal B, per clarification). Rather than widening `push_log`'s schema and risking behavior changes to its existing callers, the new `notifications` table's own `(event_type, target_type, target_id, created_at)` index answers the finer-grained question directly.

**Alternatives considered**: Adding `target_type`/`target_id` columns to `push_log` itself — rejected to avoid an in-place schema change to a table with existing production data and callers whose dedup semantics must not shift.

## R4 — Live delivery transport

**Decision**: New WS frame type `"notification"`, sent by `NativeAppInterface` over the existing `ConnectionManager.send_frame`, alongside (not replacing) the existing `trace_update`/`confirm_request` frame types.

**Rationale**: `ConnectionManager` already exists and is the single outbound WS channel; adding a frame type is the established pattern (see `trace_update`). No new transport/library is needed.

**Alternatives considered**: Server-Sent Events or a separate polling endpoint — rejected, the WebSocket connection is already the app's live channel and is open whenever the user is active, so a second channel would be redundant complexity.

## R5 — Frontend integration point

**Decision**: A new FSD `entities/notification` (types + query/mutation hooks) and `widgets/notification-bell` (dropdown panel), wired into the existing `TopBar` in place of the current decorative `<button>`.

**Rationale**: Matches the project's established FSD conventions (query hooks in `entities/<name>/api/`, widgets compose entities). The WS frame is consumed the same way `trace_update` already is — via the existing WS message dispatch in `features/invalidate-on-ws-refresh`, extended with a new case for `"notification"` frames that updates the React Query cache for the notification list/unread-count.

**Alternatives considered**: A global notification store (Zustand) mirroring `NoticeBanner`'s `notice-store.ts` pattern — rejected as the primary store; React Query already owns server-backed collections elsewhere in this app (contacts, goals, workflows), and the notification list is fundamentally server state with pagination, matching that pattern is more consistent than introducing client state for what unread count/read status already model server-side.
