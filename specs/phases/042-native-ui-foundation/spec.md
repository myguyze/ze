# Native UI Foundation — Spec

> **Package:** `ze_core` (message types + store), `ze` (WebSocket endpoint, NativeAppInterface)
> **Phase:** 42
> **Status:** Done
> **Depends on:** Phase 40 ([40-notifications.md](../040-notifications/spec.md)), Phase 1 (AppInterface ABC), Phase 7 (ProactiveNotifier)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| Message types | ✅ Done |
| `PostgresMessageStore` | ✅ Done |
| `NativeAppInterface` | ✅ Done |
| WebSocket endpoint + `ConnectionManager` | ✅ Done |
| `NtfyNotifier` (via `ze-notifications`) | ✅ Done |
| `GET /api/messages` REST endpoint | ✅ Done |
| Migration | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze currently uses Telegram as its only interface. Telegram handles message delivery,
push notifications, and session continuity for free — but it also owns the UI, imposes
format constraints (64-byte callback payloads, message size limits, no custom rendering),
and makes it impossible to display structured agent output as native components.

This phase replaces the Telegram interface with a backend foundation that a web or native
client can connect to. It introduces three things:

1. **Message persistence** — every user and agent message is written to Postgres so the
   app can load history on open, and proactive messages are never lost.
2. **WebSocket endpoint** — real-time bidirectional channel between the app and the backend.
3. **ntfy integration** — lightweight push notifications for when the app is backgrounded.

The React web client itself is out of scope here (Phase 43). This phase delivers the
backend contract that the client will consume.

---

## Responsibilities

- Persist every user message and every agent response to the `messages` table.
- Persist proactive messages (from jobs/scheduler) to the `messages` table before pushing.
- Expose a WebSocket endpoint at `/ws` for the app to send messages and receive responses in real time.
- Expose `GET /api/messages` for the app to load message history on open.
- Send ntfy push notifications for every outbound message (both reactive and proactive) so
  the user is reachable when the app is backgrounded.
- Implement `NativeAppInterface` (replacing `TelegramAppInterface`) that satisfies the
  existing `AppInterface` ABC.
- Mark messages as read when the app acknowledges them over WebSocket.

---

## Out of Scope

- React web client implementation (Phase 43).
- Component descriptors and structured rendering — those are Phase 41. The `components`
  field exists in the schema but is stored as raw JSONB and ignored by the backend until
  Phase 41.
- Multi-user or multi-device support. Ze is single-user; `ConnectionManager` holds at most
  one active WebSocket connection.
- Message editing or deletion.
- End-to-end encryption.
- File/image attachments over WebSocket (voice transcription still works via the existing
  multimodal pipeline; attachments are future scope).

---

## Module Location

```
core/ze-core/
  ze_core/
    conversation/
      messages/
        types.py          ← Message, MessageRole
        store.py          ← MessageStore ABC + PostgresMessageStore

apps/ze-api/
  ze_api/
    api/
      websocket/          ← WebSocket endpoint, ConnectionManager
      messages.py         ← GET /api/v0/messages REST endpoint
    interface/
      native.py           ← NativeAppInterface(AppInterface)
```

---

## Data Structures

```python
# ze_core/conversation/messages/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

MessageRole = Literal["user", "assistant"]

@dataclass
class Message:
    id: UUID
    role: MessageRole
    text: str | None                    # plain text body; None for component-only messages
    components: list[dict[str, Any]]    # raw component descriptors (empty until Phase 41)
    read: bool
    created_at: datetime
    thread_id: str | None               # LangGraph thread_id, for traceability
```

---

## Database Schema

```sql
-- ze-core migration zc016_messages.py

CREATE TABLE messages (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    role        TEXT        NOT NULL CHECK (role IN ('user', 'assistant')),
    text        TEXT,
    components  JSONB       NOT NULL DEFAULT '[]',
    read        BOOLEAN     NOT NULL DEFAULT FALSE,
    thread_id   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX messages_created_at_idx ON messages (created_at DESC);
CREATE INDEX messages_unread_idx     ON messages (read, created_at DESC) WHERE NOT read;
```

---

## Store Interface

```python
# ze_core/conversation/messages/store.py

class MessageStore(Protocol):
    async def save(self, message: Message) -> None: ...
    async def list_since(self, since: datetime, limit: int = 100) -> list[Message]: ...
    async def mark_read(self, ids: list[UUID]) -> None: ...
    async def list_unread(self) -> list[Message]: ...


class PostgresMessageStore:
    def __init__(self, pool: asyncpg.Pool) -> None: ...

    async def save(self, message: Message) -> None:
        # INSERT INTO messages (id, role, text, components, read, thread_id, created_at)
        # VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
        # ON CONFLICT DO NOTHING
        ...

    async def list_since(self, since: datetime, limit: int = 100) -> list[Message]:
        # SELECT ... FROM messages WHERE created_at > $1 ORDER BY created_at ASC LIMIT $2
        ...

    async def mark_read(self, ids: list[UUID]) -> None:
        # UPDATE messages SET read = TRUE WHERE id = ANY($1)
        ...

    async def list_unread(self) -> list[Message]:
        # SELECT ... FROM messages WHERE NOT read ORDER BY created_at ASC
        ...
```

---

## WebSocket Protocol

### Endpoint

```
WS /ws
Authorization: Bearer <ZE_API_KEY>
```

Single connection. If a second client connects while one is active, the first is closed
with code 4000 ("replaced by new connection").

### Client → Server frames

```json
{ "type": "message", "text": "...", "thread_id": null, "context": null }
{ "type": "ack",     "ids": ["<uuid>", "..."] }
{ "type": "ping" }
```

`context` is an optional object carrying the screen the user was on when they sent the
message. It is injected into the agent's prompt as additional context. Shape:

```json
{ "screen": "goals", "goal_id": "abc-123" }
{ "screen": "news" }
{ "screen": "reminders" }
{ "screen": "chat" }
```

The backend treats `context` as opaque metadata — it is forwarded to the routing layer
and injected into `AgentContext.extensions["screen_context"]`. Agents may read it from
their context to tailor their response. Unrecognised keys are ignored.

### Server → Client frames

```json
{ "type": "message",  "message": { ...Message } }
{ "type": "typing" }
{ "type": "error",    "detail": "..." }
{ "type": "pong" }
{ "type": "refresh",  "screen": "goals" }
```

`refresh` is emitted by the backend after a tool call mutates data owned by a named
screen. The app re-fetches that screen's data. `screen` matches the same values used in
the `context` field above. Multiple `refresh` frames may be emitted in one turn if
multiple screens are affected.

### `ConnectionManager`

```python
# ze/api/ws.py

class ConnectionManager:
    """Holds the single active WebSocket connection."""

    async def connect(self, ws: WebSocket) -> None: ...
    async def disconnect(self) -> None: ...
    async def push(self, message: Message) -> None:
        """Send a message frame if connected; silently no-ops if disconnected."""
        ...

    @property
    def connected(self) -> bool: ...
```

`ConnectionManager` is a singleton registered in `ZeContainer`. It is injected into
`NativeAppInterface` and into the proactive notifier path.

---

## Notifier

`NtfyNotifier` and the `Notifier` Protocol are defined in the `ze-notifications` package
(Phase 42). `NativeAppInterface` accepts a `Notifier` — the Protocol — not the concrete
implementation directly. See [040-notifications](../040-notifications/spec.md).

---

## NativeAppInterface

Replaces `TelegramAppInterface`. Implements the `AppInterface` ABC from `ze_core`.

```python
# ze/interface/native.py

class NativeAppInterface(AppInterface):
    def __init__(
        self,
        message_store: MessageStore,
        connection_manager: ConnectionManager,
        ntfy: NtfyClient,
    ) -> None: ...

    async def send_message(
        self,
        text: str,
        thread_id: str | None = None,
        components: list[dict] | None = None,
    ) -> None:
        msg = Message(
            id=uuid4(),
            role="assistant",
            text=text,
            components=components or [],
            read=False,
            created_at=datetime.utcnow(),
            thread_id=thread_id,
        )
        await self._store.save(msg)
        await self._conn.push(msg)          # no-op if app is not connected
        await self._ntfy.push(              # always notify
            title="Ze",
            body=text[:200],                # ntfy body truncated for notification preview
        )
```

---

## REST Endpoint

```python
# ze/api/messages.py

@router.get(
    "/api/messages",
    response_model=list[MessageSchema],
    summary="Load message history",
    description="Returns messages after `since` (ISO 8601), newest-last. Max 200.",
)
async def list_messages(
    since: datetime = Query(default=..., description="Load messages after this timestamp"),
    limit: int = Query(default=100, le=200),
    store: MessageStore = Depends(get_message_store),
) -> list[MessageSchema]:
    return await store.list_since(since, limit)
```

`MessageSchema` is a Pydantic model in `ze/api/schemas.py` mirroring the `Message` dataclass.

---

## Inbound Message Flow (WebSocket)

```
App sends { "type": "message", "text": "..." }
  → save user Message to MessageStore (role="user", read=True immediately)
  → invoke graph (same path as TelegramAppInterface today)
  → graph produces response
  → NativeAppInterface.send_message() called
      → save assistant Message (read=False)
      → push via WebSocket
      → push via ntfy
```

## Proactive Message Flow (Jobs / Scheduler)

```
ProactiveNotifier fires
  → calls NativeAppInterface.send_message()
      → save assistant Message (read=False)
      → push via WebSocket (no-op if disconnected — message is in DB for app to fetch)
      → push via ntfy (reaches user even if app is closed)
```

## App Open Flow

```
App launches → establishes WebSocket
  → server: list_unread() → push each unread message via WebSocket
  → app: renders messages in order
  → app: sends { "type": "ack", "ids": [...] }
  → server: mark_read(ids)
```

---

## Configuration

```yaml
# config/config.yaml
notifications:
  ntfy:
    base_url: "https://ntfy.sh"
    topic: "ze-joao"
```

```
# .env
NTFY_TOKEN=                  # optional; leave empty for public topics
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.interface.AppInterface` | ABC that `NativeAppInterface` satisfies |
| `ze_core.conversation.messages.MessageStore` | Persistence for all messages |
| `ze_core.proactive.ProactiveNotifier` | Calls `send_message` on proactive fire |
| `fastapi.WebSocket` | WebSocket transport |
| `ze_notifications.notifier.Notifier` | Push notification Protocol (Phase 42) |
| `aiohttp.ClientSession` | ntfy HTTP client (via `ze-notifications`) |
| `asyncpg.Pool` | Postgres connection for `PostgresMessageStore` |

---

## Implementation Notes

- **ntfy is best-effort.** A failed ntfy push must never raise. The message is already in
  Postgres — the user will see it on next app open regardless. Log the failure and continue.
- **WebSocket push is also best-effort.** `ConnectionManager.push()` catches all send
  errors silently. The source of truth is always the `messages` table, not the WebSocket.
- **Single connection invariant.** Ze is single-user. There is no concept of multiple
  simultaneous sessions. If the user opens the app on two devices, the second connection
  wins and the first is closed.
- **`read=True` for user messages immediately.** User messages are written already-read
  (the user sent them). Only assistant messages start as `read=False`.
- **Thread ID traceability.** `thread_id` on `Message` links back to the LangGraph
  checkpoint. Not surfaced in the UI in this phase but enables future "show reasoning"
  features.
- **Telegram removal.** Delete `ze/telegram/`, `TelegramAppInterface`, the aiogram
  dependency, and the Telegram-specific webhook routes. The `ZeBot` lifespan setup in
  `ze/api/` is replaced by the WebSocket lifespan setup.

---

## Testing

| Test | Location |
|------|----------|
| `PostgresMessageStore.save()` writes correct row | `core/ze-core/tests/conversation/test_message_store.py` |
| `list_since()` returns messages in ascending order | `core/ze-core/tests/conversation/test_message_store.py` |
| `mark_read()` flips read flag | `core/ze-core/tests/conversation/test_message_store.py` |
| `list_unread()` excludes already-read messages | `core/ze-core/tests/conversation/test_message_store.py` |
| `NativeAppInterface.send_message()` saves + pushes + notifies | `tests/interface/test_native.py` |
| `NativeAppInterface.send_message()` continues if WebSocket disconnected | `tests/interface/test_native.py` |
| `NativeAppInterface.send_message()` continues if ntfy raises | `tests/interface/test_native.py` |
| `ConnectionManager` closes first connection when second connects | `tests/api/test_ws.py` |
| Inbound WebSocket message invokes graph and returns response frame | `tests/api/test_ws.py` |
| `ack` frame marks messages read | `tests/api/test_ws.py` |
| App-open flow: unread messages pushed on connect | `tests/api/test_ws.py` |
| `NtfyClient.push()` sends correct headers and body | `tests/notifications/test_ntfy.py` |
| `NtfyClient.push()` swallows HTTP errors | `tests/notifications/test_ntfy.py` |
| `GET /api/messages` returns paginated history | `tests/api/test_messages.py` |

---

## Open Questions

- [x] **Should ntfy also fire for reactive responses, or only proactive?** → **Always fire.**
  The user may send a message and background the app before the response arrives. ntfy ensures
  they know it's ready. Add a `proactive: bool` field to the ntfy payload title prefix so the
  Flutter app can suppress duplicate banners when the WS connection is already open.
- [x] **WebSocket auth — Bearer token vs query param?** → **Support both.**
  Flutter's `web_socket_channel` cannot set custom headers on the HTTP→WS upgrade on iOS
  (platform restriction). FastAPI checks `Authorization: Bearer` header first, then falls back
  to `?token=<ZE_API_KEY>` query param. Both are equivalent in security for a single-user
  local/self-hosted deployment.
- [x] **What happens to existing LangGraph checkpoints when Telegram is removed?** →
  **Abandon existing checkpoints.** They are resumption state for in-flight Telegram
  conversations (e.g. paused at `await_confirmation`), not user data. Before cutover, run
  `SELECT DISTINCT thread_id FROM checkpoints WHERE ...` to confirm no active confirmations
  are pending. New sessions use `thread_id = f"ze-{uuid4()}"`.

## Pre-Mortem Findings (resolved before implementation)

### Additional protocol frames required (T2)

The spec's WebSocket protocol must include three additional server→client frame types to
replace Telegram-specific UI features:

```json
{ "type": "edit",            "id": "<message-uuid>", "text": "...", "components": [] }
{ "type": "confirm_request", "id": "<request-uuid>", "prompt": "...", "actions": [...] }
{ "type": "confirm_cancel",  "id": "<request-uuid>" }
```

And one additional client→server frame:

```json
{ "type": "command", "name": "cancel" | "costs" | "memory" | "contacts" }
```

`edit` replaces Telegram's `edit_message_text` used by progress messages (Phase 14).
`confirm_request` replaces inline keyboards used by confirmation flows.
`command` replaces `/commands`.

### ntfy token enforcement (T3)

`NtfyClient.__init__` must raise `ZeConfigError` at startup if `base_url` contains
`ntfy.sh` and `token` is `None`. Private topics are required for ntfy.sh. Self-hosted
instances may omit the token if the instance is network-isolated.

Add to `.env.example`:
```
NTFY_TOKEN=your-ntfy-token   # required for ntfy.sh; optional for self-hosted
```

### Connect-lock for race safety (T4)

`ConnectionManager.connect()` acquires an `asyncio.Lock` before flushing unread messages.
`send_message()` acquires the same lock before pushing to the live WS. This serializes the
initial unread flush with any concurrent proactive fires.

### Concurrent invocation policy (T5)

If a second `message` frame arrives while a graph invocation is in flight, the WS handler
returns an `error` frame with `detail: "busy"` and drops the frame. The Flutter app shows
a "Ze is thinking…" state and disables the send button while a response is pending.
Queuing is out of scope — Ze is a single-user assistant, not a message queue.

### Telegram hard cut (E1 / E3)

Ze is local-only with no active deployment. Telegram is **deleted in this phase** — no
parallel operation, no feature flag. The Flutter app (Phase 42) becomes the only client.

Before deleting `ze/telegram/`, the following Telegram-specific features must have
WebSocket equivalents confirmed in this spec (all resolved above):

- Phase 14 progress messages (edit-in-place) → `edit` frame ✓
- Phase 21 Telegram commands (`/costs`, `/memory`, `/contacts`, `/cancel`) → `command` frame ✓
- Phase 22 reminders firing → `send_message` (already generic) ✓
- Phase 26 stuck goal inline actions → `confirm_request` frame ✓
- Phase 29 progress messages → `edit` frame ✓

Delete: `ze/telegram/`, `TelegramAppInterface`, aiogram dependency, Telegram webhook routes,
all `TELEGRAM_*` env vars from `.env.example` and `settings.py`.
