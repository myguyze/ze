# Feature Specification: Notification Center

**Feature Branch**: `105-notification-center`

**Created**: 2026-07-13

**Status**: Implemented

**Input**: User description: "Notification Center — wire the currently-decorative Bell button in the web app top bar into a real notification feed. Persist proactive events (morning briefing, goal gates, workflow failures, calendar reminders, insight digests, weekly accountability narrative, stuck-goal alerts, goal suggestions) that today only go out as ntfy pushes, so the web client has a durable, readable history with unread state, live updates while connected, and deep links back to the source item. Usable by any plugin, not hardcoded to one domain."

## Clarifications

### Session 2026-07-13

- Q: Should notification dedup be scoped to event type only (global), or to event type + the specific target entity (e.g. per-goal, per-workflow-run)? → A: Dedup by event type + specific target entity — a stuck-goal alert for Goal A must not suppress a distinct one for Goal B.
- Q: Does opening the notification panel auto-mark visible notifications as read, or does read state only change via explicit action (click item / "mark all read")? → A: Opening the panel auto-marks the currently-visible notifications as read.
- Q: If a plugin that emitted past notifications is later disabled or uninstalled, do its historical notifications stay visible or get hidden? → A: They remain visible — a notification is a record of what happened, not a live view into the plugin's current state.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See what happened while I was away (Priority: P1)

As the user, when I open the web app after being away, I want to see a list of everything Ze proactively surfaced (briefings, alerts, digests, reminders) since I last checked, with the ones I haven't seen yet clearly marked, so I don't have to reconstruct it from ntfy push history on my phone or by hunting through chat/goals/workflows pages.

**Why this priority**: This is the entire point of the feature — without a persisted, browsable history, the bell is still decorative. Every other story builds on this one existing.

**Independent Test**: Trigger a proactive job (e.g. a workflow failure alert) against a test account, then open the web app and click the bell. The event appears in the list with an unread indicator. Delivers value on its own even with no live updates or read tracking.

**Acceptance Scenarios**:

1. **Given** a proactive job has fired an event (e.g. workflow failure) while I was not connected, **When** I open the web app and click the bell, **Then** I see that event in the list with a title, a short description, when it happened, and which area of Ze it came from.
2. **Given** I have never opened the bell, **When** I look at the top bar, **Then** I see a count of unread notifications on the bell icon.
3. **Given** I have more notifications than fit on screen, **When** I scroll the notification list, **Then** older notifications load progressively rather than all at once.

---

### User Story 2 - Notifications appear live while I'm using the app (Priority: P2)

As the user, while I'm actively using the web app, I want a new proactive event (e.g. a goal gate being reached) to show up in the bell immediately, without needing to refresh the page.

**Why this priority**: Without live delivery, the center is a stale inbox users must remember to poll — most of the value of "notification" as a concept is immediacy. This is P2 rather than P1 because a working history (P1) is still useful even if the user has to refresh to see new items.

**Independent Test**: With the web app open and connected, trigger a proactive event server-side. Within a few seconds, the bell's unread count increments and the item appears at the top of the list without a page reload.

**Acceptance Scenarios**:

1. **Given** the web app is open and connected, **When** a new proactive event fires, **Then** the unread count on the bell updates and the new item appears at the top of the list without a manual refresh.
2. **Given** the web app was disconnected when an event fired and later reconnects, **When** the connection is restored, **Then** any events missed while disconnected are still present the next time the notification list is fetched (no gaps).

---

### User Story 3 - Act on and clean up notifications (Priority: P3)

As the user, I want to mark notifications as read and jump straight to the relevant goal, workflow run, or reminder from a notification, so the bell stays useful as a triage tool rather than an ever-growing unread pile.

**Why this priority**: Read-state and navigation are quality-of-life on top of a working feed (P1) and live delivery (P2); the feature is usable without them, just less pleasant.

**Independent Test**: Open the notification list, click an item linking to a goal. The app navigates to that goal's page and the item's unread indicator clears. Reopening the bell shows the item no longer counted as unread.

**Acceptance Scenarios**:

1. **Given** an unread notification with a link to a specific goal, **When** I click it, **Then** I am taken to that goal's page and the notification is marked read.
2. **Given** several unread notifications, **When** I open the notification panel, **Then** I have a way to mark all of them as read at once.
3. **Given** a notification whose linked item (goal, workflow run, reminder) no longer exists, **When** I click it, **Then** I see a clear message that the item is no longer available instead of a broken or blank page.

---

### Edge Cases

- What happens when the same underlying event would otherwise fire a duplicate ntfy push within a job's existing dedup window (e.g. a stuck-goal alert re-checked hourly)? The in-app notification must follow the same dedup behavior — no duplicate entries for the same event type + target entity within that window — but a different target (e.g. a different goal) must still get its own notification.
- How does the system handle a burst of many events in a short window (e.g. several workflow failures at once)? The unread count and list must reflect all of them without the live-update path dropping any.
- What happens when a user clears/reads notifications on one device (e.g. mobile push acknowledgment) — does that affect the web bell's read state, or are they tracked independently? (See Assumptions.)
- What happens when a notification's deep link target has since been deleted or expired (e.g. a completed and archived goal)? The user must get a clear "no longer available" state, not an error page.
- How long is notification history retained before old, already-read items are pruned?
- A plugin that emitted a notification is later disabled/uninstalled: its historical notifications remain visible in the list (a notification is a record of what happened, not a live view into the plugin's current registration state); deep links into a now-inactive plugin's pages should still degrade to the "no longer available" state per FR-009 rather than erroring.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST persist a durable, user-facing record for every proactive event that currently only produces an ntfy push (morning briefing, goal gate reached, workflow failure alert, calendar reminder, insight digest, weekly accountability narrative, stuck-goal/anomaly alert, goal suggestion).
- **FR-002**: Each persisted notification MUST include a human-readable title, a short body/description, the time it occurred, which area of Ze it originated from (e.g. Goals, Workflows, Calendar), and an unread/read state.
- **FR-003**: Each notification MAY include a deep link to a specific goal, workflow run, reminder, or other source record.
- **FR-004**: The system MUST expose the notification history to the web client in reverse-chronological order, with the ability to fetch further back (pagination) rather than returning the entire history at once.
- **FR-005**: The system MUST expose a current unread count to the web client.
- **FR-006**: The web app top bar bell MUST display the current unread count and MUST open a list of notifications when clicked.
- **FR-007**: Opening the notification panel MUST automatically mark the notifications currently visible in it as read. Users MUST also be able to explicitly mark all notifications as read in one action (e.g. to clear items not yet scrolled into view).
- **FR-008**: Clicking a notification with a deep link MUST navigate the user to the linked item and mark that notification as read.
- **FR-009**: Clicking a notification whose linked item no longer exists MUST show a clear "no longer available" state rather than an error or blank page.
- **FR-010**: While the web app is connected, a new proactive event MUST appear in the bell (list and unread count) without requiring a manual page refresh.
- **FR-011**: Notifications MUST NOT be lost for a user who was disconnected when the event occurred — they MUST appear in the persisted history once the client next fetches it.
- **FR-012**: The system MUST NOT create duplicate notification entries for the same logical event — scoped to event type plus the specific target entity (e.g. the same goal, the same workflow run) — within the same dedup/rate-limit window that already governs that event's ntfy push. A distinct target (e.g. a different goal going stuck) MUST still produce its own notification even within that window.
- **FR-013**: Any plugin (Goals, Workflows, Calendar, Accountability, News, Finance, etc.) MUST be able to emit a notification through a common mechanism, without the notification system having hardcoded knowledge of any single plugin's domain.
- **FR-014**: Confirmation requests that require a user decision (goal/workflow gate approvals) MUST continue to be handled through the existing in-chat confirmation flow and MUST NOT be duplicated as separate items in the notification bell.
- **FR-015**: The system MUST retain notification history for a bounded period, after which old, already-read notifications are eligible for removal (default: 90 days for read items; unread items retained indefinitely until read — see Assumptions).

### Key Entities

- **Notification**: A single proactive event surfaced to the user. Attributes: event type, title, body, source plugin/area, created time, read/unread state, optional deep link (type + id of the linked goal/workflow run/reminder/etc.).
- **Notification Source**: The plugin, job, or domain area that emitted the notification (e.g. "goals", "workflows", "calendar", "accountability") — used for display grouping/iconography and for routing deep links. Recorded as a durable label on the notification itself, independent of whether that plugin is still active — a disabled/uninstalled source's past notifications remain visible.
- **Unread Count**: A derived, per-user count of notifications not yet marked read, surfaced on the bell.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of the proactive event types that currently only produce an ntfy push (briefing, goal gate, workflow failure, calendar reminder, insight digest, weekly narrative, stuck-goal alert, goal suggestion) also appear in the in-app notification history.
- **SC-002**: A user who was connected to the web app sees a new proactive event reflected in the bell's unread count within 5 seconds of the event occurring server-side.
- **SC-003**: A user who was disconnected when events fired sees 100% of those events in their notification history the next time they open the app — zero silently dropped events.
- **SC-004**: A user can go from "unread notification in the bell" to "viewing the linked goal/workflow/reminder" in two clicks or fewer.
- **SC-005**: No duplicate notification entries are created for the same logical event within that event type's existing dedup window (verified against at least the stuck-goal-alert and workflow-failure-alert event types, which already rate-limit their ntfy pushes).
- **SC-006**: Marking all notifications as read clears the unread badge to zero in a single user action.

## Assumptions

- ntfy push delivery is retained as-is for offline/disconnected delivery; this feature adds a persisted, in-app history and live in-app delivery alongside it — it does not replace ntfy.
- Read/unread state is tracked per notification in the web app only; acknowledging an ntfy push on a phone does not mark the corresponding in-app notification as read, since there is no existing cross-channel read-state sync in Ze today.
- This is a single-user system (per project scope), so there is no per-recipient fan-out or multi-user notification targeting to design for.
- Existing WS confirmation frames (goal/workflow gate approvals) and the in-page `NoticeBanner` context notices are explicitly out of scope for this feature and continue to work as they do today.
- A reasonable default retention window (see FR-015) applies unless the user specifies otherwise; unbounded growth of the notification table is out of scope for v1.
- The notification list is a flat reverse-chronological feed for v1; grouping/digesting multiple related notifications into one entry (e.g. "3 workflow failures today") is out of scope unless a future phase requires it.
