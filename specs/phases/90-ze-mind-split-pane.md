# Phase 90 — Ze's Mind Split-Pane

**Status:** Done
**Depends on:** Phase 89 (Message Trace), Phase 45 (Native App Interface / WebSocket)
**Packages touched:** `core/ze-core`, `apps/ze-api`, `apps/ze-web`

---

## What this is

A collapsible right panel in the chat UI that shows Ze's "working memory" for the
current conversation turn — live context retrieved, active routing, tool calls in
progress. The panel updates as each response arrives, so the user feels Ze thinking
rather than receiving a finished answer from a black box.

Whereas Phase 89 (Message Trace) is a *post-hoc* audit trail, this phase is a
*real-time* observation window. After graph completion, the panel auto-populates
from the trace of the most recent message.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Live data delivery | Dedicated WebSocket frame type `trace_update` during graph execution | Avoids polling; graph nodes emit partial trace frames as they run |
| Post-response state | Pull trace from Phase 89 `getMessageTrace` endpoint once WS frame arrives with `message_id` | Single source of truth — WS frame carries live data, REST trace is the durable record |
| Panel persistence | Toggle stored in `localStorage` (open/closed) | User preference survives page refresh |
| Panel width | 320 px, resizable via drag handle (min 240 px, max 480 px) | Complements 720 px chat column on typical 1280 px+ screen |
| Mobile | Panel hidden on < 768 px viewport; accessible from "Brain" icon in toolbar | Mobile screen too narrow for split view |
| Sections | Routing · Memory · Tools (same as Trace panel) | Consistent with Phase 89 layout; live ≈ post-hoc |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `trace_update` WebSocket frame type | ✅ Done |
| Graph nodes emit partial trace frames | ✅ Done (emitted once post-graph, before message frame) |
| `ZeMindPanel` React component | ✅ Done |
| Panel toggle in chat toolbar | ✅ Done |
| Width drag handle | ✅ Done |
| Mobile fallback | ✅ Done (hidden on <768px) |

---

## WebSocket frame: `trace_update`

The backend emits this frame from the `NativeAppInterface` as the graph runs. Because
graph execution is not streamed (Phase 45 decision: `ainvoke` not `astream_events`),
the frame is emitted *once* at the end of graph execution — just before the `message`
frame — carrying the completed trace.

If streaming is adopted in future, the same frame shape can carry partial updates by
setting `partial: true` and omitting fields not yet known.

```typescript
// apps/ze-web/src/shared/ws/types.ts
interface TraceUpdateFrame {
  type: "trace_update";
  message_id: string;
  agent: string;
  routing_method: string;
  confidence: number;
  score_gap: number;
  is_compound: boolean;
  subtasks: string[];
  memory_chunks: Array<{ text: string; score: number; source: string }>;
  tool_calls: Array<{
    name: string;
    result_snippet: string;
    duration_ms: number;
    success: boolean;
  }>;
  total_duration_ms: number;
}
```

### Backend emission (`ze_api/interface/native.py`)

After `record_trace` runs in the graph, the interface already has the completed
`AgentState`. Emit the `trace_update` frame immediately before the `message` frame:

```python
async def deliver(self, result: AgentResult, state: AgentState) -> None:
    # emit trace first (if available)
    if trace := state.get("_trace"):
        await self._ws_send({"type": "trace_update", **asdict(trace)})
    # then message
    await self._ws_send({"type": "message", ...})
```

The `_trace` key is populated by the `record_trace` node (Phase 89) and passed back
in the state dict.

---

## Frontend (`apps/ze-web`)

### Layout

```
┌────────────────────────────────┬──────────────────────────────┐
│           Chat                 │       Ze's Mind              │
│                                │  (320 px, collapsible)       │
│  [Message bubbles…]            │                              │
│                                │  ┌──────────────────────┐   │
│                                │  │ companion • 94%       │   │
│                                │  │ embedding · direct    │   │
│                                │  ├──────────────────────┤   │
│                                │  │ ▾ Memory (3)          │   │
│                                │  │   fact 0.91 …         │   │
│                                │  │   episode 0.87 …      │   │
│                                │  ├──────────────────────┤   │
│                                │  │ ▾ Tools (2)           │   │
│                                │  │   search_web 312ms ✓  │   │
│                                │  │   get_calendar 88ms ✓ │   │
│                                │  └──────────────────────┘   │
│  [Input bar]                   │                              │
└────────────────────────────────┴──────────────────────────────┘
```

### FSD layout

```
widgets/ze-mind-panel/
  ui/
    ZeMindPanel.tsx       # container: toggle, resize handle, section list
    RoutingSection.tsx    # agent badge, method, confidence bar, compound flag
    MemorySection.tsx     # retrieved chunks (same as Phase 89 MemoryChunkList)
    ToolsSection.tsx      # tool call list (same as Phase 89 ToolCallList)
    EmptyState.tsx        # "Send a message to see Ze's thinking"
features/ze-mind-state/
  model/
    useMindStore.ts       # Zustand slice: current trace, panel open state, width
    useTraceSocket.ts     # subscribes to "trace_update" WS frames
```

### State management

`useMindStore` (Zustand):

```typescript
interface MindState {
  open: boolean;
  width: number;                // px, default 320
  trace: TraceUpdateFrame | null;
  toggle: () => void;
  setTrace: (t: TraceUpdateFrame) => void;
  setWidth: (w: number) => void;
}
```

`useTraceSocket` listens to the shared WebSocket store and calls `setTrace` when a
`trace_update` frame arrives.

### Resize handle

A 4 px drag handle on the left edge of the panel. `mousedown` → `mousemove` updates
`width` in the store; clamped to [240, 480]. Width is persisted to `localStorage` via
a `zustand/middleware/persist` wrapper.

### Transitions

When a new message is submitted, the panel shows a "Ze is thinking…" spinner overlay
on the existing (stale) trace until the `trace_update` frame arrives for the new
message. This prevents the panel from going blank.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| Phase 89 `MessageTrace` types | Shared shape between WS frame and REST trace |
| `trace_update` WS frame | Real-time trace delivery |
| `getMessageTrace` (Phase 89) | Fallback if user opens panel on old message |
| Zustand | Panel state (open, width, current trace) |
| `localStorage` | Width + open state persistence |

---

## Out of scope

- Streaming partial updates mid-graph-execution (requires switching from `ainvoke` to
  `astream_events` — a separate architectural decision).
- Displaying raw LLM prompt or token counts.
- Pinning specific memory chunks from the panel (Phase 88 feed handles curation).

---

## Testing

| Area | Tests |
|------|-------|
| `useTraceSocket` | Receives `trace_update` frame → updates store |
| `ZeMindPanel` | Renders routing/memory/tools sections from mock trace |
| Resize handle | Clamps width; persists to localStorage |
| Empty state | Shows when no trace yet; shows spinner during pending response |
| Mobile | Panel is hidden on narrow viewport |
