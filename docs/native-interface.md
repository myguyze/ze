# Ze — Native App Interface

Ze's native interface connects the React web app (`ze-web`) to the backend (`ze-api`)
over a persistent WebSocket. When the app is not connected, Ze falls back to
**ntfy push notifications**.

**Module:** `ze_api/interface/native.py` · `ze_api/api/ws.py`  
**WebSocket endpoint:** `GET /ws`

---

## Overview

```
React App ←──── WebSocket /ws ────→ NativeAppInterface
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
3. If a confirmation was pending when the client disconnected, replays the
   `confirm_request` frame so the user can still approve or cancel (see
   [Confirmation flow](#confirmation-flow)).
4. Begins forwarding new messages in real time.

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
| `{"type": "command", "name": "costs"}` | Introspection | Returns a 7-day cost summary message |
| `{"type": "command", "name": "status", "period_days": 1}` | Accountability | Returns an activity narrative (default: past 24 h; set `period_days: 7` for the weekly view) |
| `{"type": "command", "name": "onboarding"}` | Setup | Starts or resumes onboarding |
| `{"type": "command", "name": "reset_preview", "scope": "memory"}` | Reset preview | Returns counts for a reset scope |
| `{"type": "command", "name": "reset", "scope": "memory", "confirm": "RESET"}` | Reset | Executes a scoped reset; requires explicit confirmation |
| `{"type": "component_submit", "session_id": "...", "step_id": "...", "component_id": "...", "values": {...}}` | Interactive component | Submits structured onboarding form/button values |

### Server → Client

| Frame | Description |
|---|---|
| `{"type": "pong"}` | Heartbeat reply |
| `{"type": "typing"}` | Sent immediately after receiving a user message while Ze is processing. May include an optional `"text"` field with a localized progress string (e.g. `"📡 Fetching the latest news..."`). Re-sent mid-turn by agents to update the status and reset the client's 3-second display timer. |
| `{"type": "message", "message": Message}` | Outbound message from Ze (see Message shape below) |
| `{"type": "confirm_request", "id": "...", "prompt": "...", "actions": [...]}` | Capability gate confirmation request |
| `{"type": "confirm_cancel", "id": "..."}` | Confirmation cancelled (timeout or cancel command) |
| `{"type": "error", "detail": "..."}` | Error from the server (e.g. "busy") |

### Progress messages

The `typing` frame carries an optional `text` field with a localized human-readable
status string. The server sends an initial `{ "type": "typing" }` (no text) as soon
as a user message is received; agents then emit keyed progress messages mid-turn that
re-send the frame with text.

```json
{ "type": "typing", "text": "📡 Fetching the latest news..." }
```

Each `typing` frame resets the client's display timer (default 3 seconds). Long-running
operations (e.g. RSS fetches, web searches) emit multiple frames to keep the indicator
alive.

Clients should render `text` when present and fall back to a generic spinner when absent.
`typingText` is exposed from `useChatSession` for this purpose.

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
The web app renders them below the message text.

Onboarding messages also include an `onboarding` metadata object beside `message`:

```json
{
  "type": "message",
  "message": { "role": "assistant", "text": "Setup", "components": [] },
  "onboarding": { "session_id": "uuid", "completed": false }
}
```

The web app stores this metadata on the message and uses it when form/confirm
components submit `component_submit` frames.

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
the same `thread_id`.

### Persistence across disconnects

The `confirm_request` payload is saved to the `pending_confirmations` Postgres table
at the moment it is sent. On the next WebSocket reconnect, after replaying unread
messages, the server checks `pending_confirmations` for any non-expired row and
re-sends the `confirm_request` frame. The user can approve or cancel even if they
closed and reopened the app.

The row is cleared when:
- The user responds (approve or cancel).
- The timeout elapses (see below).

### ntfy push on background

When the app is not connected and a confirmation is required, Ze also pushes an ntfy
notification with the prompt text (urgency `high`) so the user is alerted even with
the app closed.

### Timeout

A `CONFIRM_TIMEOUT_SECONDS` (default: 900 s / 15 min) watchdog runs in the background
from the moment the `confirm_request` is sent. If the window elapses with no user
response, Ze sends:

```
"I waited for your approval but the window elapsed — let me know if you'd like me to try again."
```

The `pending_confirmations` row is deleted. If the app is still connected the message
appears in-chat; otherwise it goes via ntfy (urgency `low`).

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
| `connect(ws, message_store, confirmation_store=None)` | Accept a new connection; closes the previous one; replays unread messages; replays any pending confirmation |
| `disconnect()` | Clear the active connection |
| `push(message)` | Send a message frame; silently no-ops if disconnected |
| `send_frame(frame)` | Send an arbitrary JSON frame |
| `try_set_busy() → bool` | Claim the invocation slot; returns False if already busy |
| `clear_busy()` | Release the invocation slot |

Never instantiate `ConnectionManager` outside the FastAPI lifespan — there must only
be one instance.
