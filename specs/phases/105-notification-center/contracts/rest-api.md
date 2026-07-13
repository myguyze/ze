# Contract: REST API — Notifications

All routes under `/api/v0/notifications`, authenticated via the existing `require_api_key` dependency (`HTTPBearer`), tagged `notifications`. Follows the existing route conventions in `apps/ze-api/ze_api/api/routes/` (explicit `operation_id`, `response_model`, `summary`, `description` on every route — constitution/CLAUDE.md OpenAPI rule).

## `GET /api/v0/notifications`

Reverse-chronological, cursor-paginated notification list.

**Query params**:
- `cursor: str | None` — opaque pagination cursor (created_at + id of the last item seen).
- `limit: int = 20` (max 100).
- `unread_only: bool = False` — filter to unread items.
- `mark_read: bool = False` — when true, atomically marks every notification returned in this page as read before responding (implements "opening the panel auto-marks visible items as read", Clarification 2026-07-13). The web client's panel-open fetch sets this to true; background/prefetch calls leave it false.

**Response** (`NotificationListResponse`):
```json
{
  "items": [ { "...": "Notification shape, see data-model.md" } ],
  "next_cursor": "string | null"
}
```

## `GET /api/v0/notifications/unread-count`

**Response** (`UnreadCountResponse`):
```json
{ "count": 3 }
```

## `POST /api/v0/notifications/{id}/read`

Marks a single notification read. Idempotent — reading an already-read notification is a no-op success.

**Response**: `204 No Content`. `404` if `id` does not exist.

## `POST /api/v0/notifications/read-all`

Marks every currently-unread notification read (FR-007's explicit "mark all as read" action, for items not yet scrolled into view).

**Response** (`MarkAllReadResponse`):
```json
{ "marked": 12 }
```

## Error handling

- Unknown `cursor` value → `400` with a clear message (client should refetch from the start).
- All routes return standard Ze error envelope on failure (typed `ZeError` subclasses per `ze_api/errors.py`), no bare exceptions.
