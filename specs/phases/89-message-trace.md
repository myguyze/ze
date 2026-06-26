# Phase 89 — Message Trace ("Why did Ze do that?")

**Status:** Pending
**Depends on:** Phase 73 (API surface), Phase 82 (ze-web FSD), Phase 87 (Plugin UI)
**Packages touched:** `core/ze-core`, `apps/ze-api`, `apps/ze-web`

---

## What this is

Per-message explainability: for every AI response, expose which agent handled it, how
confident the router was, what memory chunks were retrieved, and what tools were called.
The user can open a collapsible "Why?" panel beneath any message and see Ze's reasoning
chain.

This phase also lays the data foundation for Phase 92 (Agent Activity Heatmap) and
Phase 90 (Ze's Mind Split-Pane), both of which aggregate or display this trace data.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Trace storage | `trace` JSONB column on `messages` table | Avoids a new join table; traces are always read with the message; JSONB is schema-flexible as trace fields evolve |
| Trace capture point | `synthesize` graph node (final node before `write_memory`) | All execution data is settled at this point — agent, envelope, memory context |
| Memory context in trace | Top-k retrieved chunks (text + score), not IDs | IDs may be vacuumed; including text makes traces self-contained |
| Tool calls in trace | Summary list from `AgentResult.tool_calls` | Full tool I/O is too large; names + one-line result snippet is enough |
| API endpoint | `GET /api/v0/messages/{message_id}/trace` | Lazy-loaded — don't fetch on initial chat load |
| Frontend trigger | "Why?" icon button on AI message hover | Non-intrusive; only visible on hover |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `zc_trace` migration (add `trace` column to `messages`) | 🔲 Pending |
| `MessageTrace` dataclass in `ze_core/conversation/messages/types.py` | 🔲 Pending |
| Trace capture in `synthesize` node | 🔲 Pending |
| `MessageStore.save_trace()` method | 🔲 Pending |
| `GET /api/v0/messages/{message_id}/trace` route | 🔲 Pending |
| Schema types in `schemas.py` | 🔲 Pending |
| Codegen update | 🔲 Pending |
| `MessageTracePanel` component | 🔲 Pending |
| "Why?" hover button on AI messages | 🔲 Pending |

---

## Database

### Migration

Branch: `zc` (continues ze-core chain). Add a nullable JSONB column — no backfill needed;
old messages simply have no trace.

```sql
ALTER TABLE messages ADD COLUMN IF NOT EXISTS trace JSONB NULL;

CREATE INDEX IF NOT EXISTS messages_trace_agent_idx
    ON messages ((trace->>'agent'))
    WHERE trace IS NOT NULL;
```

---

## Core types (`ze_core/conversation/messages/types.py`)

```python
@dataclass
class MemoryChunkTrace:
    text: str
    score: float
    source: str          # "fact" | "episode" | "profile"

@dataclass
class ToolCallTrace:
    name: str
    result_snippet: str  # first 200 chars of result
    duration_ms: int
    success: bool

@dataclass
class MessageTrace:
    agent: str
    routing_method: str          # "embedding" | "haiku" | "fallback"
    confidence: float
    score_gap: float
    is_compound: bool
    subtasks: list[str]          # agent names of subtasks
    memory_chunks: list[MemoryChunkTrace]
    tool_calls: list[ToolCallTrace]
    total_duration_ms: int
```

---

## Graph node change (`ze_core/orchestration/nodes/`)

In the `synthesize` node (or a new `record_trace` node immediately after), capture:

```python
async def record_trace(state: AgentState, config: dict) -> dict:
    envelope = state.get("envelope")
    agent_result = state.get("agent_result")
    memory_context = state.get("memory_context")  # list[RetrievedChunk]

    if envelope is None or agent_result is None:
        return {}

    trace = MessageTrace(
        agent=envelope.primary_agent,
        routing_method=envelope.routing_method,
        confidence=envelope.confidence,
        score_gap=envelope.score_gap,
        is_compound=envelope.is_compound,
        subtasks=[s.agent for s in envelope.subtasks],
        memory_chunks=[
            MemoryChunkTrace(
                text=c.text[:300],
                score=c.score,
                source=c.source,
            )
            for c in (memory_context or [])
        ],
        tool_calls=[
            ToolCallTrace(
                name=t.name,
                result_snippet=(t.result or "")[:200],
                duration_ms=t.duration_ms,
                success=t.success,
            )
            for t in (agent_result.tool_calls or [])
        ],
        total_duration_ms=agent_result.duration_ms,
    )
    # Save trace alongside the message id
    # message_id is set on AgentState by the write_message node
    configurable = config.get("configurable", {})
    message_store: MessageStore = configurable["message_store"]
    message_id = state.get("message_id")
    if message_id:
        await message_store.save_trace(message_id, trace)

    return {}
```

`record_trace` is inserted as a node after `synthesize` and before `write_memory` in the
graph builder.

---

## MessageStore extension

```python
class MessageStore(Protocol):
    # existing methods …
    async def save_trace(self, message_id: UUID, trace: MessageTrace) -> None: ...
    async def get_trace(self, message_id: UUID) -> MessageTrace | None: ...
    async def list_with_agent(
        self,
        start: datetime,
        end: datetime,
    ) -> list[tuple[UUID, str, datetime]]: ...  # (message_id, agent, created_at) for heatmap
```

`PostgresMessageStore` implementation:

```python
async def save_trace(self, message_id: UUID, trace: MessageTrace) -> None:
    async with self._pool.acquire() as conn:
        await conn.execute(
            "UPDATE messages SET trace = $1::jsonb WHERE id = $2",
            json.dumps(asdict(trace)),
            message_id,
        )

async def get_trace(self, message_id: UUID) -> MessageTrace | None:
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT trace FROM messages WHERE id = $1", message_id
        )
    if row is None or row["trace"] is None:
        return None
    return _parse_trace(row["trace"])
```

---

## REST API (`apps/ze-api`)

### `GET /api/v0/messages/{message_id}/trace`

Returns the trace for a single AI message.

```python
class MemoryChunkTraceResponse(BaseModel):
    text: str
    score: float
    source: str

class ToolCallTraceResponse(BaseModel):
    name: str
    result_snippet: str
    duration_ms: int
    success: bool

class MessageTraceResponse(BaseModel):
    agent: str
    routing_method: str
    confidence: float
    score_gap: float
    is_compound: bool
    subtasks: list[str]
    memory_chunks: list[MemoryChunkTraceResponse]
    tool_calls: list[ToolCallTraceResponse]
    total_duration_ms: int
```

- **operation_id:** `getMessageTrace`
- **Auth:** `require_api_key`
- **404** when message not found or trace is `NULL` (pre-Phase-89 message).

---

## Frontend (`apps/ze-web`)

### "Why?" button

On hover of any AI message bubble, show a small `Info` (Lucide) icon in the top-right
corner. Click opens the `MessageTracePanel` below the message (slide-down animation,
collapses on second click).

### `MessageTracePanel`

```
widgets/message-trace/
  ui/
    MessageTracePanel.tsx    # lazy-fetches trace on first open
    TraceSection.tsx         # collapsible section (routing / memory / tools)
    RoutingBadge.tsx         # agent name + routing method chip + confidence bar
    MemoryChunkList.tsx      # list of retrieved chunks with score badges
    ToolCallList.tsx         # tool call rows with name, snippet, duration, ✓/✗
```

**Panel layout:**

```
┌─────────────────────────────────────────────────┐
│ Handled by: companion  •  embedding  •  94% conf │
│ Score gap: 0.31  •  Direct (not compound)        │
├─────────────────────────────────────────────────┤
│ ▾ Memory retrieved (3 chunks)                   │
│   [fact 0.91] "User prefers concise answers"    │
│   [episode 0.87] "Discussed travel plans…"      │
│   [fact 0.82] "User is based in Lisbon"         │
├─────────────────────────────────────────────────┤
│ ▾ Tools called (2)                              │
│   search_web  •  312ms  •  ✓                    │
│   get_calendar  •  88ms  •  ✓                   │
└─────────────────────────────────────────────────┘
```

- Sections are individually collapsible.
- If `trace` is null (old message), show "No trace available for this message."
- Fetched via `getMessageTrace` from `@ze/client`; cached in TanStack Query by message id.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `messages.trace` column (new) | Persistent trace storage |
| `AgentState.envelope` | Routing data |
| `AgentState.memory_context` | Retrieved chunks |
| `AgentResult.tool_calls` | Tool execution log |
| `GET /api/v0/messages/{id}/trace` | Lazy trace fetch |
| Phase 92 (Heatmap) | Consumes `list_with_agent()` |
| Phase 90 (Split-Pane) | Consumes live trace during graph execution |

---

## Out of scope

- Streaming trace updates during graph execution (Phase 90 handles live context).
- Exposing raw LLM prompt/response text.
- Trace diffing across re-runs.

---

## Testing

| Area | Tests |
|------|-------|
| `record_trace` node | Correct `MessageTrace` built from mock `AgentState` |
| `MessageStore.save_trace` / `get_trace` | Round-trip via real SQL |
| `GET /api/v0/messages/{id}/trace` | Returns 200 with trace; 404 for missing/null |
| `MessageTracePanel` | Renders all three sections; shows fallback for null trace |
