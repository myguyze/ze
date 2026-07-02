# Phase 99 — Multi-Conversation Support

> **Status:** Pending
> **Depends on:** Phase 45 — NativeAppInterface, ConnectionManager, WebSocket transport
> **Enables:** Side-by-side chat panels, conversation history navigation without losing context
> **Packages touched:** `core/ze-core`, `apps/ze-api`, `apps/ze-web`

---

## Summary

Ze currently allows only one conversation at a time. A new WebSocket connection displaces the
existing one, and all server-to-client frames are sent to whichever socket is open — with no
concept of which conversation they belong to. This phase makes multiple concurrent conversations
a first-class feature. A single persistent WebSocket carries all frames for all threads;
every frame is tagged with `thread_id` so the client can route delivery to the correct chat
window. LangGraph already isolates state by `thread_id`; the database already stores messages
and confirmations per-thread. The work is in the transport and delivery layer only — no domain
logic changes required.

---

## Goals

- Multiple conversations can run concurrently without interrupting each other.
- Switching between conversations does not require reconnecting the WebSocket.
- All server-to-client frames carry `thread_id`; the client routes each frame to the correct chat view.
- Per-thread busy state: one thread being processed does not block another from submitting.
- Pending confirmations are replayed to the correct conversation on reconnect.
- ntfy push only fires for a thread when that thread has no active in-session routing.
- `ChatNavGroup` rows show a spinner while a thread is busy (processing a message).
- `ChatNavGroup` rows show a blinking attention dot when a thread requires user action (confirmation request, new unread message from a background run).
- When the chat nav group is collapsed, the attention dot bubbles up to the parent "Chat" row in the sidebar.

## Non-Goals

- Multi-user / multi-account support (Ze is single-user).
- Conversation branching or forking within a thread.
- Shared conversation panels / split-view UI (UI decides layout; this phase only enables the transport).
- Persistence of "open conversations" across page reloads beyond what the session store already does.

---

## Background

The current single-connection design lives in two places:

- **`ConnectionManager`** (`apps/ze-api/ze_api/api/websocket/connection.py`): holds `self._ws: WebSocket | None`, a single `_busy: bool`, and a single `_pending_gate_redirect`. A new `connect()` call closes the previous socket with code `4000`.
- **`NativeAppInterface`** (`apps/ze-api/ze_api/interface/native.py`): receives `thread_id` in `send_with_thread()` but ignores it for delivery — `push()` blindly sends to whatever socket is active.

LangGraph is already multi-conversation capable: `configurable.thread_id` scopes every checkpoint. The `messages` table has a `thread_id` column with an index. The `pending_confirmations` table uses `thread_id` as its primary key. The client already sends `thread_id` in every outbound `message` frame. The gaps are purely in the transport layer.

---

## Design

### Approach: Multiplexed Single WebSocket

One persistent WebSocket connection for the entire session. Every frame in both directions
carries a `thread_id`. The server routes delivery by `thread_id` without opening additional
sockets. This is the natural evolution of what already exists — the client already sends
`thread_id` in message frames, and `NativeAppInterface.send_with_thread()` already receives it.

### ConnectionManager Redesign

Replace the single-slot design with a per-thread slot map:

```python
# connection.py (conceptual)
@dataclass
class ThreadSlot:
    ws: WebSocket
    busy: bool = False
    pending_config: dict | None = None
    pending_gate_redirect: UUID | None = None

class ConnectionManager:
    _slots: dict[str, ThreadSlot]   # thread_id → slot
    _ws: WebSocket | None           # the single shared socket

    async def connect(self, ws: WebSocket) -> None:
        # Close previous socket if present (single WS invariant)
        if self._ws is not None:
            await self._ws.close(4000)
        self._ws = ws
        # Replay unread messages + pending confirmations for ALL known threads
        # (or only threads the client declares active — see Open Questions)

    def register_thread(self, thread_id: str) -> None:
        if thread_id not in self._slots:
            self._slots[thread_id] = ThreadSlot(ws=self._ws)

    async def push(self, msg: Message, thread_id: str) -> None:
        # Send via self._ws; frame carries thread_id

    async def send_frame(self, frame: dict, thread_id: str) -> None:
        # Send via self._ws; frame carries thread_id

    def is_busy(self, thread_id: str) -> bool:
        return self._slots.get(thread_id, ThreadSlot(ws=None)).busy

    def set_busy(self, thread_id: str, busy: bool) -> None:
        ...
```

The `_ws` remains a single socket (multiplexed). Per-thread state (`busy`, `pending_config`,
`pending_gate_redirect`) moves into `ThreadSlot`.

### Frame Protocol Changes

Every server-to-client frame gains a top-level `thread_id: str` field. This is the only
breaking change to the frame schema.

**Server → Client — updated frames:**

| Frame type | Change |
|---|---|
| `message` | Already has `thread_id` via `MessageSchema` — no change needed |
| `typing` | Add `thread_id: str` |
| `token` | Add `thread_id: str` |
| `error` | Add `thread_id: str` |
| `trace_update` | Add `thread_id: str` |
| `confirm_request` | Add `thread_id: str` |
| `confirm_cancel` | Add `thread_id: str` |
| `edit` | Add `thread_id: str` |
| `refresh` | Add `thread_id: str` (screen refresh for a specific thread's context) |

**Client → Server — updated frames:**

| Frame type | Change |
|---|---|
| `message` | Already has `thread_id` — no change |
| `confirm` | Add `thread_id: str` so the server knows which slot's `pending_config` to resume |
| `ack` | No change needed — message IDs are globally unique |
| `component_submit` | Already has optional `thread_id` — make it required |

### NativeAppInterface

`send_with_thread(message, thread_id)` already exists and already receives `thread_id`.
Change `self._conn.push(msg)` → `self._conn.push(msg, thread_id)`. Same for `send_frame`
calls in `send_trace_partial()` and friends.

ntfy fallback logic changes: fire ntfy only when `thread_id` has no active slot in
`ConnectionManager` (i.e. `_ws is None` or the thread has never been registered). Currently
ntfy fires whenever `push_notifier` is set, regardless of connection state.

### Pending Confirmations

`PendingConfirmationStore.get_any_pending()` returns any non-expired row. On reconnect this
can replay a confirmation from the wrong thread. Change to
`get_pending_for_thread(thread_id: str)` and call it once per active thread at connection
time.

`confirmation_timeout()` currently calls `conn_mgr.send_frame()` with no thread routing.
Change to pass `thread_id` (already stored in the DB row).

`handle_confirm()` reads `pending_config` from the WS handler's in-memory state — currently
a single `dict | None`. Move to `ConnectionManager.slots[thread_id].pending_config`.

### WS Endpoint

`endpoint.py` currently accepts `thread_id` as a query param and uses it only for unread
replay. Under the new model, `thread_id` in the URL is no longer needed (threads are
registered dynamically as messages arrive). Remove the `thread_id` query param requirement;
register a thread slot on first message for that thread.

Alternatively, keep the query param for initial unread replay of a "primary" thread but
allow any thread to be active once connected. Document the choice in Architectural Decisions.

### React Client

#### `ws-client.ts`

- Remove `getThreadId` getter and the URL-embedded `thread_id`.
- Remove `reconnect()` call on session switch — switching threads no longer requires a new WS connection.
- `dispatch(frame)` routes each incoming frame by `frame.thread_id` to the appropriate handler set. Handler registration becomes `on(type, thread_id, handler)` (or handlers filter by thread_id themselves — see below).

#### `useWsStore`

- `isThinking` becomes `Map<string, boolean>` (`thread_id → boolean`).
- Expose `isThinkingForThread(thread_id: string): boolean` selector.

#### `useChatWorkspace`

- Receives `threadId` as a parameter (already does via `sessionThreadId`).
- Add thread filtering to `typing`, `token`, `error` frame handlers (currently unfiltered).
- Read `isThinkingForThread(threadId)` instead of global `isThinking`.

#### `session-store.ts` / `bootstrap-ws.ts`

- `newSession()` still mints a UUID and makes it the "active" thread — but no longer triggers a WS reconnect.
- `bootstrap-ws.ts`: remove the `threadId`-change → `reconnect()` subscription. The WS connects once and stays connected.
- On initial connect, send a `subscribe` frame listing the threads the client wants to track (for replay ordering). This is optional — see Open Questions.

#### `ChatNavGroup`

- `selectSession(id)` now just updates the active thread in the store (no reconnect).
- The WS stays open; the new thread's messages will arrive tagged with its `thread_id`.

#### `ChatNavGroup` — Per-Thread Status Affordances

Each session row in `ChatNavGroup` shows two possible status indicators, mutually exclusive,
checked in this priority order:

1. **Spinner** — shown when `isThinkingForThread(thread_id)` is `true`. Ze is actively
   processing a message for this conversation. The spinner replaces or overlays the session
   icon/avatar in the row.

2. **Attention dot** — a small pulsing/blinking dot shown when the thread requires user
   action but Ze is not actively processing. Triggers:
   - A `confirm_request` frame has arrived for this thread and has not been answered.
   - A new `message` frame arrived for this thread while it was not the active conversation
     (background response from a prior message on an inactive thread).

   The dot clears when:
   - The user opens the conversation (thread becomes active).
   - The confirmation is answered (`confirm_cancel` frame received or user submits).

State to track per-thread in the client store (extend `useWsStore` or a new
`useThreadStatusStore`):

```typescript
interface ThreadStatus {
  isThinking: boolean;         // busy — spinner
  needsAttention: boolean;     // unread response or pending confirm — dot
}

// Map<thread_id, ThreadStatus>
```

#### Sidebar Bubble-Up — Chat Nav Row

When `ChatNavGroup` is collapsed (the "Chat" group is folded in the sidebar), the attention
state of any thread inside it must surface to the group's parent nav row:

- If **any** thread in the group has `needsAttention: true`, the "Chat" nav row displays
  the blinking attention dot.
- If **any** thread has `isThinking: true` (and none need attention), the "Chat" nav row
  displays the spinner.
- When the group is expanded, the row-level indicators on `ChatNavGroup` take over and
  the group-level indicators are hidden.

This means `AppShell` / `NavGroup` (or whatever renders the sidebar group header) must
receive the aggregate status from the thread status store and render accordingly. The
aggregate is derived:

```typescript
const anyThinking  = threads.some(t => status[t.id]?.isThinking);
const anyAttention = threads.some(t => status[t.id]?.needsAttention);
```

---

## Interface Contract

### WebSocket Frames

All frames below are server → client unless noted.

```typescript
// All server-to-client frames gain thread_id
interface BaseFrame {
  type: string;
  thread_id: string;   // NEW on all frames
}

interface TypingFrame extends BaseFrame {
  type: "typing";
  text?: string;
}

interface TokenFrame extends BaseFrame {
  type: "token";
  text: string;
}

interface ErrorFrame extends BaseFrame {
  type: "error";
  detail: string;
}

interface TraceUpdateFrame extends BaseFrame {
  type: "trace_update";
  message_id: string;
  partial: boolean;
  agent?: string;
  // ...existing fields
}

interface ConfirmRequestFrame extends BaseFrame {
  type: "confirm_request";
  id: string;
  prompt: string;
  actions: ConfirmAction[];
}

interface ConfirmCancelFrame extends BaseFrame {
  type: "confirm_cancel";
  id: string;
}

interface EditFrame extends BaseFrame {
  type: "edit";
  id: string;
  text?: string;
  components?: Component[];
}

// Client → Server
interface ConfirmFrame {
  type: "confirm";
  thread_id: string;   // NEW — required
  id: string;
  choice: "approve" | "deny" | "edit";
}

interface ComponentSubmitFrame {
  type: "component_submit";
  thread_id: string;   // was optional, now required
  step_id: string;
  values: Record<string, unknown>;
}
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Message sent for a thread with no registered slot | Register slot on-the-fly; process normally |
| `confirm` frame arrives with unknown `thread_id` | Return `error` frame: `"no pending confirmation for thread"` |
| Two messages submitted for the same thread concurrently | Second is rejected with `error` frame: `"thread busy"` (per-thread busy flag) |
| Two messages submitted for different threads concurrently | Both processed concurrently — no interference |
| WS disconnected while a thread is mid-run | Run continues; response delivered on reconnect via unread replay |
| ntfy fires for a thread that reconnects before the user taps | ntfy notification is stale but harmless; unread replay on reconnect already shows the message |

---

## Data Structures

No new database tables. No new domain types. Changes are confined to internal WS-layer types.

```python
# apps/ze-api/ze_api/api/websocket/connection.py

@dataclass
class ThreadSlot:
    busy: bool = False
    pending_config: dict | None = None
    pending_gate_redirect: UUID | None = None
```

---

## Database Schema

No schema changes required.

- `messages.thread_id` — already exists, already indexed.
- `pending_confirmations.thread_id` — already the primary key.
- `sessions.id` — unchanged.

---

## Migration / Rollout Notes

- No Alembic migration needed.
- The frame protocol change (`thread_id` on all server-to-client frames) is breaking for the
  existing client. Ship server and client together; no version negotiation needed (single-user,
  controlled deployment).
- Old client behaviour: if `thread_id` is absent on a frame, the client falls back to the
  active session's `threadId`. This allows a phased rollout where server ships first if
  needed, though simultaneous deploy is preferred.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `core/ze-core` | `ConnectionManager`, `NativeAppInterface`, `PendingConfirmationStore` |
| `apps/ze-api` | WS endpoint, `handle_confirm`, `handle_message` |
| `apps/ze-web` | `ws-client.ts`, `useWsStore`, `useChatWorkspace`, `session-store.ts`, `bootstrap-ws.ts` |

---

## Alternatives Considered

| Option | Why rejected |
|--------|-------------|
| One WebSocket per conversation | Opens N sockets for N active threads. More server-side complexity managing N connections. Reconnect-on-switch is the current behaviour we are trying to eliminate. |
| Keep single WS, add thread_id only to new frame types | Inconsistent protocol; client still cannot reliably route frames from currently-untagged types (typing, error, token). All-or-nothing is cleaner and avoids a second pass. |
| Thread-id in HTTP header / cookie instead of frames | Does not work for a multiplexed socket where multiple threads are active simultaneously. |

---

## Testing Strategy

| Layer | What to cover | Approach |
|-------|--------------|----------|
| Unit | `ConnectionManager` routes `push(msg, thread_id)` to correct frame | pytest, mock WS |
| Unit | `ThreadSlot.busy` prevents concurrent runs on same thread, allows different threads | pytest |
| Unit | `get_pending_for_thread()` returns only matching row | pytest, mock asyncpg |
| Unit | `send_with_thread()` passes `thread_id` to `ConnectionManager.push()` | pytest |
| Integration | Two concurrent messages on different `thread_id`s both complete | real asyncpg, mock LLM |
| Integration | Pending confirmation replayed only to correct thread on reconnect | real asyncpg |
| Client | `useChatWorkspace` typing/token/error handlers filter by `thread_id` | vitest |
| Client | `isThinkingForThread` returns correct per-thread state | vitest |
| Client | Spinner appears on nav row when thread is busy; clears on response | vitest |
| Client | Attention dot appears on background response; clears on navigation to thread | vitest |
| Client | Attention dot appears on `confirm_request`; clears on `confirm_cancel` or answer | vitest |
| Client | Collapsed group: dot/spinner aggregates to "Chat" row; disappears when group expands | vitest |
| Manual | Open two chat tabs; send message on each; verify no cross-contamination | browser |
| Manual | Send message on inactive tab; verify attention dot on nav row and on parent "Chat" row when collapsed | browser |

---

## Definition of Done

- [ ] `ConnectionManager` uses `ThreadSlot` dict; single `_ws`; per-thread busy flag
- [ ] `NativeAppInterface.push()` / `send_frame()` pass `thread_id` to `ConnectionManager`
- [ ] All server-to-client frame schemas include `thread_id`
- [ ] `confirm` and `component_submit` client frames require `thread_id`
- [ ] `PendingConfirmationStore.get_pending_for_thread(thread_id)` implemented
- [ ] Unread replay on connect scoped per-thread
- [ ] `confirmation_timeout()` routes frame by `thread_id`
- [ ] `handle_confirm()` reads `pending_config` from `ThreadSlot`
- [ ] ntfy fires only when thread has no active connection
- [ ] React: WS does not reconnect on session switch
- [ ] React: `isThinking` is per-thread
- [ ] React: `typing`, `token`, `error` handlers filter by `thread_id`
- [ ] `ChatNavGroup` rows show spinner when thread is busy
- [ ] `ChatNavGroup` rows show blinking attention dot for unread background responses and pending confirmations
- [ ] Attention dot clears when conversation is opened or confirmation is resolved
- [ ] When `ChatNavGroup` is collapsed, aggregate spinner/dot bubbles up to the "Chat" sidebar row
- [ ] Unit tests for `ConnectionManager` routing and `ThreadSlot` busy semantics
- [ ] Unit tests for `get_pending_for_thread()`
- [ ] Client tests for per-thread frame filtering
- [ ] Client tests for thread status store (spinner set/clear, attention set/clear)
- [ ] Client tests for aggregate bubble-up when group is collapsed
- [ ] Spec status updated → Done; `specs/README.md` row added

---

## Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single multiplexed WS vs one WS per thread | Multiplexed single WS | Fewer open sockets; no reconnect on thread switch; natural extension of existing design where client already sends thread_id in outbound frames |
| `thread_id` in URL query param | Remove as requirement | With multiplexing, thread_id comes from each frame; no longer meaningful at connection URL. Keep for optional initial replay hint. |
| Unread replay scope on reconnect | Replay all unread across all known threads | User may have messages in multiple conversations; replaying all ensures no message is missed. Alternative: replay only threads the client declares — deferred to Open Questions. |
| ntfy fallback condition | Fire when `ConnectionManager._ws is None` | Simplest check; avoids per-thread "is the user looking at this thread?" logic which requires client-side presence signalling not in scope. |

---

## Open Questions

- [ ] Should the client send a `subscribe` frame on connect listing the thread IDs it wants replayed? This would allow targeted replay (only threads the user has open) rather than replaying all unread. — João — before implementation starts
- [ ] Should there be a maximum number of concurrently registered threads in `ConnectionManager`? (Memory/GC concern if a user creates many conversations.) — João — before implementation starts
- [ ] Does the URL `?thread_id=` param stay for backward compatibility, or is it removed immediately? — João — before implementation starts
