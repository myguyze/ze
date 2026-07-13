# Contract: WebSocket — `notification` frame

Sent by `NativeAppInterface` over the existing `ConnectionManager.send_frame`, alongside the established `trace_update` / `confirm_request` frame types documented in `ws_schema.py`. Emitted once per newly created `Notification` row, only while the client is connected (FR-010) — this is additive to, not a replacement for, ntfy delivery while disconnected.

## Frame shape

```json
{
  "type": "notification",
  "id": "uuid",
  "event_type": "string",
  "source": "string",
  "title": "string",
  "body": "string",
  "target_type": "string | null",
  "target_id": "string | null",
  "created_at": "ISO 8601 timestamp",
  "read": false
}
```

`read` is always `false` on this frame — a notification is only ever pushed live at creation time, before any read action can have occurred.

## Client handling

The existing WS frame dispatcher (`features/invalidate-on-ws-refresh`) gains a case for `type === "notification"`:
- Prepend the item to the cached first page of `GET /api/v0/notifications`.
- Increment the cached unread count by 1.

No client action is required to keep history consistent on reconnect: the REST list (`contracts/rest-api.md`) is the source of truth and is always re-fetched on reconnect per the standard `RefreshHandler` pattern already used elsewhere in the app, covering FR-011 (no gaps for events missed while disconnected).
