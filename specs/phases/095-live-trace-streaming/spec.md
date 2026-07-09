# Phase 95 — Unified Streaming Architecture

**Status:** Pending
**Depends on:** Phase 90 (Ze's Mind Split-Pane — `trace_update` WS frame and panel)
**Packages touched:** `core/ze-core`, `apps/ze-api`, `apps/ze-web`

---

## What this is

Makes the entire response lifecycle visible as a live stream in the Ze's Mind
panel. Today the lifecycle looks like:

```
[user sends] → [spinner] → [full response + full trace appear at once]
```

After this phase it looks like:

```
[user sends]
  → routing decision appears (agent badge, confidence)
  → memory chunks fill in as context is fetched
  → tool calls appear and complete one by one
  → LLM tokens stream into the message bubble (already works today)
  → trace entry finalises
```

**Token streaming for messages already exists.** `BaseAgent` calls
`client.stream_complete_with_tools` which pushes `token` WS frames as the
LLM generates. The gap is graph-level events — routing, context, tool calls —
which are only available after `graph.ainvoke` completes. This phase fills
that gap by switching to `graph.astream_events`.

---

## Current streaming state (what already works)

| Stream | Mechanism | Status |
|--------|-----------|--------|
| LLM tokens → message bubble | `token_sink` → `token` WS frame | ✅ Done (Phase 45) |
| Progress text (routing/typing label) | `reporter.report()` → `typing` WS frame | ✅ Done (Phase 54) |
| Trace summary (post-graph) | `trace_update` WS frame after `ainvoke` | ✅ Done (Phase 90) |
| Routing decision (live) | ❌ blocked by `ainvoke` | 🔲 This phase |
| Memory fetch (live) | ❌ blocked by `ainvoke` | 🔲 This phase |
| Tool calls (live, one by one) | ❌ blocked by `ainvoke` | 🔲 This phase |

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph execution | Switch `graph.ainvoke` → `graph.astream_events` in `invoke_raw_turn` | Only `astream_events` exposes node-level events in real time |
| Token delivery | Keep `token_sink` pattern; tap `on_chat_model_stream` in the event loop | No change to `BaseAgent` or `LLMClient` |
| Partial trace frames | Add `partial: bool` to `WsTraceUpdateFrame`; emit one partial per node group | Reuses the existing frame type; no new WS message type needed |
| Frame ordering | routing partial → context partial → tool partials → `partial: false` final | Matches the graph execution order; frontend can render as they arrive |
| Final REST trace | `record_trace` node still runs; REST `GET /messages/{id}/trace` unchanged | Durable audit trail unaffected by streaming |

---

## WebSocket frame additions

### `WsTraceUpdateFrame` — add `partial` field

```python
class WsTraceUpdateFrame(BaseModel):
    type: Literal["trace_update"]
    message_id: str
    partial: bool = False      # true = merge into pending entry; false = commit
    agent: str = ""
    routing_method: str = ""
    confidence: float = 0.0
    score_gap: float = 0.0
    is_compound: bool = False
    subtasks: list[str] = []
    memory_chunks: list[MemoryChunkTraceResponse] = []
    tool_calls: list[ToolCallTraceResponse] = []
    total_duration_ms: int = 0
```

**Merge semantics (frontend):** `partial: true` → shallow-merge scalars,
*append* lists. `partial: false` → commit the merged entry to the trace thread.

---

## Backend: `invoke_raw_turn` with `astream_events`

Replace `graph.ainvoke(input, config)` in `ze_core/container.py`:

```python
final_state = {}
async for event in self.graph.astream_events(graph_input, config, version="v2"):
    kind  = event["event"]
    name  = event.get("name", "")
    data  = event.get("data", {})

    # ── LLM token stream (already works today, same path) ──────────────
    if kind == "on_chat_model_stream":
        chunk = data.get("chunk", {}).content or ""
        if chunk and token_sink:
            await token_sink(chunk)

    # ── Routing decided ─────────────────────────────────────────────────
    elif kind == "on_chain_end" and name == "embed_route":
        env = (data.get("output") or {}).get("envelope")
        if env and interface:
            await interface.send_trace_partial(message_id, {
                "agent": env.primary_agent,
                "routing_method": env.routing_method,
                "confidence": env.confidence,
                "score_gap": env.score_gap,
                "is_compound": env.is_compound,
                "subtasks": [s.agent for s in env.subtasks] if env.is_compound else [],
            })

    # ── Memory / context fetched ─────────────────────────────────────────
    elif kind == "on_chain_end" and name == "fetch_context":
        memory_ctx = (data.get("output") or {}).get("memory_context")
        if memory_ctx and interface:
            await interface.send_trace_partial(message_id, {
                "memory_chunks": _extract_memory_chunks(memory_ctx),
            })

    # ── One tool call completed ──────────────────────────────────────────
    elif kind == "on_tool_end":
        if interface:
            await interface.send_trace_partial(message_id, {
                "tool_calls": [_tool_event_to_trace(data)],
            })

    # ── Graph completed ──────────────────────────────────────────────────
    elif kind == "on_chain_end" and name == self.graph.name:
        final_state = data.get("output") or {}
```

`send_trace_partial` on `NativeAppInterface` emits:
```python
async def send_trace_partial(self, message_id: str, fields: dict) -> None:
    await self._conn.send_frame({
        "type": "trace_update",
        "message_id": message_id,
        "partial": True,
        **fields,
    })
```

The final `trace_update` with `partial: False` is still emitted from
`_send_message` (after `record_trace` has run and the trace is saved to the
DB), exactly as today.

---

## Frontend: `useMindStore` — partial frame merging

```typescript
interface MindState {
  ...
  pendingTrace: Partial<WsTraceUpdateFrame> | null;  // in-flight partial
  mergePartialTrace: (fields: Partial<WsTraceUpdateFrame>) => void;
  commitPendingTrace: (final: WsTraceUpdateFrame) => void;
}
```

`mergePartialTrace`:
- scalars: overwrite
- `memory_chunks` / `tool_calls`: append (never deduplicate — server controls emission)

`commitPendingTrace`: moves `pendingTrace` → `appendTrace(final)`; clears `pendingTrace`.

`useTraceSocket`:
```typescript
useFrame("trace_update", (frame) => {
  if (frame.partial) {
    mergePartialTrace(frame);
  } else {
    commitPendingTrace(frame);
  }
});
```

### Panel: live section headers

While `pendingTrace` exists, each section header shows a pulsing indicator
if its data is not yet populated:

- Routing: pulsing if `pendingTrace.agent` is empty
- Memory: pulsing if `pendingTrace.memory_chunks?.length === 0`
- Tools: pulsing if `pendingTrace.tool_calls?.length === 0`

The pending entry renders below the committed thread entries, above the
"Ze is thinking…" footer, using the same `TraceEntry` layout but marked
live with a subtle border highlight.

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `partial` field on `WsTraceUpdateFrame` | 🔲 Pending |
| `send_trace_partial` on `NativeAppInterface` | 🔲 Pending |
| `invoke_raw_turn` switched to `astream_events` | 🔲 Pending |
| Routing partial emission (`embed_route` node) | 🔲 Pending |
| Context partial emission (`fetch_context` node) | 🔲 Pending |
| Tool-call partial emission (`on_tool_end`) | 🔲 Pending |
| `mergePartialTrace` / `commitPendingTrace` in `useMindStore` | 🔲 Pending |
| `useTraceSocket` partial vs. final routing | 🔲 Pending |
| Live pending entry in panel with section pulse indicators | 🔲 Pending |

---

## Testing

| Area | Tests |
|------|-------|
| `invoke_raw_turn` | Emits routing partial → context partial → tool partials in order |
| `mergePartialTrace` | Lists append, never replace; scalars overwrite |
| `commitPendingTrace` | Moves pending entry to thread; clears pendingTrace |
| `useTraceSocket` | Partial → merge; final → commit; error → clear pending |
| Panel pulse indicators | Visible for empty sections; gone once data arrives |
| Token streaming | Unchanged — tokens still stream word by word into message bubble |

---

## Out of scope

- Showing raw LLM prompt or system message content.
- Per-subtask streaming for compound messages.
- Streaming the `synthesize` node mid-LLM-generation within the trace
  (tokens already appear in the message bubble — no duplication needed).
- Backpressure / rate-limiting of partial frames.
