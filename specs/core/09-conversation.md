> ⚠️ **Status: Stale** — Written pre-split (Phases 1–20). References `ze_core/...` paths that no longer exist. See the [package specs below](../README.md#ze-core-specs-core) for current documentation.

---

# Ze Core — Conversation Persistence — Spec

## Purpose

Platform conversation persistence for Ze: message history, session metadata, and
confirmation replay state. These stores are transport-agnostic — ze-api consumes
them via WebSocket and REST, but ownership lives in ze-core alongside the engine.

## Responsibilities

- Persist user and assistant messages for history load, unread replay, and
  background delivery (`messages` table).
- Track per-thread session metadata: title, preview, last activity (`sessions` table).
- Persist in-flight `confirm_request` payloads so they survive WebSocket
  disconnects (`pending_confirmations` table).
- Expose `MessageStore`, `SessionStore`, and `PendingConfirmationStore` protocols
  with Postgres implementations.

## Identity model

`sessions.id` is the canonical conversation identifier. On every turn it matches:

- `messages.thread_id`
- LangGraph `configurable.thread_id`
- `AgentState.session_id`

## Module layout

```
core/ze-core/ze_core/conversation/
  turn.py          # make_graph_input, invoke_raw_turn, resume_turn, TurnResult
  messages/
    types.py       # Message, MessageRole
    store.py       # MessageStore, PostgresMessageStore
  sessions/
    types.py       # Session
    store.py       # SessionStore, PostgresSessionStore
  confirmations/
    store.py       # PendingConfirmationStore
```

Public re-exports from `ze_core.conversation`.

## Migration ownership

| Revision | Table(s) |
|----------|----------|
| `zc015` | LangGraph checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`) |
| `zc016` | `messages` |
| `zc017` | `pending_confirmations` |
| `zc018` | `sessions` + `messages_thread_id_idx` |

All migrations live in `ze_core/migrations/versions/`. ze-api runs the meta-migrator
but owns no tables.

## Consumers

- `ze_api/container.py` — wires stores into DI
- `ze_api/interface/native.py` — persists outbound assistant messages
- `ze_api/api/websocket/` — turn handling, reconnect replay, confirmation flow
- `ze_api/api/routes/sessions.py`, `messages.py` — REST history endpoints
- Data portability engine domains: `messages.store`, `sessions`, `confirmations`

## Out of Scope

- `memory_session_summaries` — ze-memory retrieval concern (phase 65)
- Graph `pending_confirmation` flag — orchestration state in `AgentState`, not DB
- `accountability_anomalies` — ze-automation (`zc014`)

## Testing

Unit tests in `core/ze-core/tests/conversation/` using mocked asyncpg pools.
WS integration tests remain in `apps/ze-api/tests/api/`.
