# Data Model: Notification Center

## Notification

Owned by `ze-proactive` (`zpro` migration chain, continues from `zpro001_push_log`). One row per user-facing proactive event.

| Field | Type | Notes |
|---|---|---|
| `id` | UUID, PK | |
| `event_type` | text, not null | e.g. `"workflow_failure"`, `"goal_gate"`, `"stuck_goal"`, `"morning_brief"`, `"insight_digest"`, `"accountability_narrative"`, `"goal_suggestion"`, `"calendar_reminder"` |
| `source` | text, not null | Owning plugin/domain area label, e.g. `"goals"`, `"workflows"`, `"calendar"`, `"accountability"`, `"personal"` — a durable display label, not a foreign key; remains valid even if that plugin is later disabled (Clarification, 2026-07-13) |
| `title` | text, not null | Human-readable headline |
| `body` | text, not null | Short description |
| `target_type` | text, nullable | Deep-link target kind, e.g. `"goal"`, `"workflow_run"`, `"reminder"`; null for events with no single linked entity (e.g. morning briefing) |
| `target_id` | text, nullable | Opaque id of the linked entity within `target_type`'s domain |
| `created_at` | timestamptz, not null, default now() | |
| `read_at` | timestamptz, nullable | Null = unread |

**Indexes**:
- `(created_at DESC)` — reverse-chronological pagination (FR-004).
- `(event_type, target_type, target_id, created_at)` — dedup lookups scoped to event type + target entity (FR-012, Clarification R3).
- `(read_at) WHERE read_at IS NULL` — unread-count query (FR-005).
- `(read_at) WHERE read_at IS NOT NULL` — supports the retention-pruning sweep (FR-015) filtering on age of already-read rows.

**Validation rules**:
- `target_type` and `target_id` are both null or both set (never one without the other).
- `event_type`, `source`, `title`, `body` are required, non-empty.

**Retention**: rows with `read_at` older than 90 days are eligible for pruning (FR-015 default); rows with `read_at IS NULL` are retained indefinitely regardless of age.

**Lifecycle**: create-only + one mutation (`read_at` set once, never unset). No update to any other field after creation — a notification is an immutable record of what happened (Clarification, 2026-07-13).

## Relationship to existing `push_log`

`push_log` (existing, unchanged) continues to answer the coarse "was this event category sent recently" question used by jobs like the morning briefing (event-type-only dedup window). `notifications` is a separate table answering the finer "was this exact event-type + target already surfaced" question (Clarification R1/R3) — the two are not merged; a job may consult both (e.g. `push_log` for "don't send another morning briefing digest within 20h" and `notifications` for "don't create a second stuck-goal alert for this same goal within N hours").

## Notification (API / WS shape)

The wire representation exposed to the web client (REST list items and the `notification` WS frame payload) is a flat projection of the row above, plus a derived `read: bool`:

```
{
  "id": "uuid",
  "event_type": "string",
  "source": "string",
  "title": "string",
  "body": "string",
  "target_type": "string | null",
  "target_id": "string | null",
  "created_at": "ISO 8601 timestamp",
  "read": "boolean"
}
```
