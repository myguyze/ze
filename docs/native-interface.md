# Ze — Native App Interface

Ze's native interface connects the Flutter app (`ze-app`) to the backend (`ze-api`)
over a persistent WebSocket. When the app is not connected, Ze falls back to
**ntfy push notifications**.

**Module:** `ze_api/interface/native.py` · `ze_api/api/ws.py`  
**WebSocket endpoint:** `GET /ws`

---

## Overview

```
Flutter App ←──── WebSocket /ws ────→ NativeAppInterface
                                              │
                                     ┌────────┴─────────┐
                                     ▼                   ▼
                              MessageStore           NtfyNotifier
                          (Postgres messages)    (push when offline)
```

`NativeAppInterface` is the `AppInterface` implementation for the native client. It
saves every outbound message to `MessageStore` (for unread replay on reconnect), pushes
it to the active WebSocket connection if one exists, and falls back to ntfy if the
client is offline.

**One connection at a time.** A new WebSocket connection displaces the previous one
with close code `4000`.

---

## Authentication

Pass the API key either as a bearer header or a query parameter:

```
Authorization: Bearer <ZE_API_KEY>
# or
GET /ws?token=<ZE_API_KEY>
```

Connections without a valid key are closed with code `4001`.

---

## Connection sequence

On connect, the server:

1. Closes any previous connection with code `4000`.
2. Fetches all unread messages from `MessageStore` and replays them as
   `{"type": "message", ...}` frames.
3. Begins forwarding new messages in real time.

The client should send `{"type": "ack", "ids": [...]}` frames to mark messages as read.

---

## Frame types

### Client → Server

| Frame | When to send | Description |
|---|---|---|
| `{"type": "ping"}` | Heartbeat | Server replies with `{"type": "pong"}` |
| `{"type": "ack", "ids": ["<uuid>", ...]}` | After displaying messages | Marks messages as read in `MessageStore` |
| `{"type": "message", "text": "...", "thread_id": "...", "context": {...}}` | User sends a message | `thread_id` is optional; `context` is optional screen context |
| `{"type": "command", "name": "cancel"}` | Cancel pending confirmation | Aborts the awaited graph turn |
| `{"type": "command", "name": "costs"}` | Introspection | Returns a cost summary message |

### Server → Client

| Frame | Description |
|---|---|
| `{"type": "pong"}` | Heartbeat reply |
| `{"type": "typing"}` | Sent immediately after receiving a user message while Ze is processing |
| `{"type": "message", "message": Message}` | Outbound message from Ze (see Message shape below) |
| `{"type": "confirm_request", "id": "...", "prompt": "...", "actions": [...]}` | Capability gate confirmation request |
| `{"type": "confirm_cancel", "id": "..."}` | Confirmation cancelled (timeout or cancel command) |
| `{"type": "error", "detail": "..."}` | Error from the server (e.g. "busy") |

### Message shape

```json
{
  "id": "uuid",
  "role": "assistant",
  "text": "string",
  "components": [],
  "read": false,
  "thread_id": "string or null",
  "created_at": "ISO8601"
}
```

`components` is a list of server-driven UI component descriptors (from `ze-components`).
The Flutter app renders them below the message text.

---

## Confirmation flow

When an agent action requires user approval (`confirm` capability mode), the graph
pauses at `await_confirmation`. The server sends:

```json
{
  "type": "confirm_request",
  "id": "request-uuid",
  "prompt": "Ze proposes to send an email to João about...",
  "actions": [
    {"label": "Approve", "payload": "yes"},
    {"label": "Cancel",  "payload": "no"}
  ]
}
```

The client presents this to the user. On user action, the client sends a message:

```json
{"type": "message", "text": "yes", "thread_id": "<original-thread-id>"}
```

The WS handler resumes the LangGraph checkpoint with `graph.ainvoke(None, config)` on
the same `thread_id`. A 15-minute timeout (`CONFIRM_TIMEOUT_SECONDS`) applies — if
no response arrives the pause expires and the graph unblocks automatically.

---

## Busy guard

Only one graph invocation runs at a time. If the client sends a second `message` frame
while a previous invocation is still in flight, the server responds:

```json
{"type": "error", "detail": "busy"}
```

The client should queue or display this as feedback.

---

## Unread message replay

`MessageStore` (`ze_core/messages/store.py`) persists all outbound messages (assistant
and Ze's proactive pushes) to Postgres. On WebSocket connect, all messages with
`read = false` are replayed in order before new messages flow. The client marks them
read via `ack` frames.

**REST fallback** — `GET /messages` returns the same unread list for scenarios where the
client needs to poll rather than hold a persistent connection.

---

## ntfy push notifications

When no WebSocket connection is active, `NativeAppInterface` also delivers to ntfy
via `NtfyNotifier` (`ze-notifications`). Configure in `.env`:

```
NTFY_BASE_URL=https://ntfy.sh        # or your self-hosted instance
NTFY_TOPIC=ze-your-unique-topic
NTFY_TOKEN=                          # optional auth token for private topics
```

ntfy priority:
- Normal messages → priority 3 (default)
- High-urgency proactive notifications (e.g. workflow failures) → priority 5

If `NTFY_TOPIC` is empty, ntfy delivery is disabled and Ze is WebSocket-only.

---

## Screen context

The `message` frame accepts an optional `context` object for screen-aware responses:

```json
{
  "type": "message",
  "text": "What is this?",
  "context": {
    "screen": "GoalDetail",
    "goal_id": "uuid"
  }
}
```

The context is passed as `screen_context` in the graph config's `configurable` dict,
making it available to agents via `ctx.config`.

---

## Connection manager

`ConnectionManager` (`ze_api/api/ws.py`) is instantiated once at startup and stored
on `app.state.connection_manager`. It exposes:

| Method | Description |
|---|---|
| `connect(ws, message_store)` | Accept a new connection; closes the previous one; replays unread messages |
| `disconnect()` | Clear the active connection |
| `push(message)` | Send a message frame; silently no-ops if disconnected |
| `send_frame(frame)` | Send an arbitrary JSON frame |
| `try_set_busy() → bool` | Claim the invocation slot; returns False if already busy |
| `clear_busy()` | Release the invocation slot |

Never instantiate `ConnectionManager` outside the FastAPI lifespan — there must only
be one instance.
