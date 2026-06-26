# Phase 95 — Live Trace Streaming

**Status:** Pending
**Depends on:** Phase 90 (Ze's Mind Split-Pane — establishes `trace_update` WS frame and panel)
**Packages touched:** `core/ze-core`, `apps/ze-api`, `apps/ze-web`

---

## What this is

Replaces the post-hoc single `trace_update` frame with a stream of partial
frames emitted as each graph node completes. The Ze's Mind panel fills in
progressively — routing appears first, then memory chunks, then tool calls —
rather than flipping from spinner to fully-populated in one step.

Phase 90 deliberately deferred this (the frame shape includes `partial: true`
for exactly this reason). This phase implements it.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Graph execution mode | Switch `invoke_raw_turn` from `graph.ainvoke` to `graph.astream_events` | Only `astream_events` exposes node-level completion events in real time |
| Event tap | Subscribe to `on_chain_end` events where `name` matches known nodes | Clean; no changes to node internals required |
| Frame cadence | One partial `trace_update` per meaningful node completion (routing, context, each tool call) | Avoids frame flood while keeping panel visibly alive |
| Final frame | `partial: false` frame after `record_trace` completes — same as Phase 90 today | Downstream consumers (REST trace endpoint) remain unchanged |
| Token streaming | Token sink stays on `astream_events` `on_chat_model_stream` events — no behaviour change | Token streaming already works; don't break it |

---

## Frame shape (unchanged from Phase 90)

The `WsTraceUpdateFrame` already supports partial updates:

```typescript
interface TraceUpdateFrame {
  type: "trace_update";
  message_id: string;
  partial: boolean;          // true = merge into current entry; false = finalise
  agent: string;             // may be "" on early partials
  routing_method: string;
  confidence: number;
  score_gap: number;
  is_compound: boolean;
  subtasks: string[];
  memory_chunks: Array<{ text: string; score: number; source: string }>;
  tool_calls: Array<{ name: string; result_snippet: string; duration_ms: number; success: boolean }>;
  total_duration_ms: number;
}
```

**Merge semantics (frontend):** when `partial: true`, shallow-merge fields
that are non-empty into the current pending entry. Lists (`memory_chunks`,
`tool_calls`) are appended, not replaced. Scalar fields overwrite.

---

## Backend changes

### 1. Add `partial` field to `WsTraceUpdateFrame` (`ze_api/api/schemas.py`)

```python
class WsTraceUpdateFrame(BaseModel):
    type: Literal["trace_update"]
    message_id: str
    partial: bool = False      # ← new; False = final
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

### 2. Switch `invoke_raw_turn` to `astream_events` (`ze_core/container.py`)

Replace `graph.ainvoke(...)` with `graph.astream_events(...)` and collect
the final state from the `on_chain_end` event for the root graph.

```python
async def invoke_raw_turn(self, thread_id, raw_input, config_extra=None):
    ...
    final_state = None
    async for event in graph.astream_events(input, config, version="v2"):
        kind = event["event"]
        name = event.get("name", "")

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"].content
            if chunk and token_sink:
                await token_sink(chunk)

        elif kind == "on_chain_end" and name == "embed_route":
            # routing is decided — emit partial frame
            await _emit_routing_partial(conn, message_id, event["data"]["output"])

        elif kind == "on_chain_end" and name == "fetch_context":
            # memory retrieved — emit partial with chunks
            await _emit_context_partial(conn, message_id, event["data"]["output"])

        elif kind == "on_tool_end":
            # one tool call completed
            await _emit_tool_partial(conn, message_id, event["data"])

        elif kind == "on_chain_end" and name == graph.name:
            final_state = event["data"]["output"]

    return _build_outcome(final_state, config)
```

### 3. Remove `trace_update` emission from `NativeAppInterface._send_message`

The interface still saves the trace (for the REST endpoint) but no longer
emits the WS frame — `invoke_raw_turn` emits it directly.

---

## Frontend changes (`apps/ze-web`)

### `useMindStore` — merge partial frames

Add `mergePartialTrace(partial: Partial<WsTraceUpdateFrame>)` action:

```typescript
mergePartialTrace: (partial) => set((s) => {
  const current = s.pendingTrace ?? emptyTrace();
  return {
    pendingTrace: {
      ...current,
      ...partial,
      memory_chunks: [...current.memory_chunks, ...(partial.memory_chunks ?? [])],
      tool_calls: [...current.tool_calls, ...(partial.tool_calls ?? [])],
    },
  };
}),
```

When `partial: false` arrives, move `pendingTrace` → `appendTrace(frame)`.

### `useTraceSocket` — handle partial flag

```typescript
useFrame("trace_update", (frame) => {
  if (frame.partial) {
    mergePartialTrace(frame);
  } else {
    appendTrace(frame);
  }
});
```

### Panel — live section headers

While a partial is pending, section headers show a pulsing dot next to their
title (`memory_chunks.length === 0 && pending` → "Memory ●"). Once chunks
arrive, the dot disappears and the list renders normally.

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `partial` field on `WsTraceUpdateFrame` | 🔲 Pending |
| `invoke_raw_turn` switched to `astream_events` | 🔲 Pending |
| Node-level partial frame emission (routing, context, tools) | 🔲 Pending |
| `NativeAppInterface` trace emission removed | 🔲 Pending |
| `mergePartialTrace` in `useMindStore` | 🔲 Pending |
| `useTraceSocket` partial handling | 🔲 Pending |
| Live section header pulse indicators | 🔲 Pending |

---

## Testing

| Area | Tests |
|------|-------|
| `invoke_raw_turn` | Emits routing partial before context partial before tool partials |
| `mergePartialTrace` | Lists append; scalars overwrite; no duplicate dedup |
| `useTraceSocket` | Partial frames go to merge; final frame commits entry |
| Panel headers | Pulse dot visible during partial; gone after final frame |

---

## Out of scope

- Mid-LLM-generation token-level reasoning (showing the synthesise prompt
  mid-flight) — requires exposing raw prompt content.
- Per-subtask partial traces for compound messages.
- Backpressure / rate-limiting of partial frames.
