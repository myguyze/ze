> ⚠️ **Status: Stale** — Written pre-split (Phases 1–20). References `ze_core/...` paths that no longer exist. See the [package specs below](../README.md#ze-core-specs-core) for current documentation.

---

# Ze Core — Orchestration Graph — Spec

## Purpose

Define the LangGraph state machine that coordinates routing, capability checking,
context fetching, agent execution, response synthesis, and memory writing. The
graph is the central nervous system of a Ze Core application — it owns execution
flow and nothing else. Individual nodes are thin wrappers that delegate to domain
modules.

---

## Responsibilities

- Define `AgentState` as the single source of truth for graph state.
- Define all graph nodes as pure async functions in `ze_core/orchestration/nodes/`.
- Define all conditional edges as pure functions in `ze_core/orchestration/edges.py`.
- Compile and expose the LangGraph graph in `ze_core/orchestration/graph.py`
  via `graph_builder()` (extensible) and `build_graph()` (default topology).
- Persist graph state via `AsyncPostgresSaver` (survives restarts).
- Handle human-in-the-loop pausing via `interrupt_before=["await_confirmation"]`.
- Enforce per-agent timeouts via `asyncio.wait_for`.
- Support parallel branch execution for compound non-sequential tasks.

## Out of Scope

- Does not implement agent logic (delegates to registered agent classes).
- Does not implement capability evaluation (delegates to `CapabilityGate`).
- Does not implement memory storage (delegates to `MemoryStore`).
- Does not manage transport connections (delegates to `AppInterface`).
- Does not choose tools.

---

## AgentState

`ze_core/orchestration/state.py`

```python
class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]   # "agent.intent" → mode string

    # ── Multimodal ─────────────────────────────────────────────────────────
    input_modality: str         # "text" | "voice" | "image" — default "text"
    audio_data: bytes | None    # raw audio bytes; cleared by preprocess after transcription
    audio_mime: str | None      # e.g. "audio/ogg; codecs=opus"
    image_data: bytes | None    # raw image bytes; None for text/voice turns
    image_mime: str | None      # "image/jpeg" | "image/png" | None
    image_caption: str | None   # caption generated at preprocess; None until set

    # ── Routing ────────────────────────────────────────────────────────────
    envelope: RoutingEnvelope | None

    # ── Context ────────────────────────────────────────────────────────────
    memory_context: MemoryContext | None
    agent_context: AgentContext | None

    # ── Capability ─────────────────────────────────────────────────────────
    gate_decision: GateDecision | None

    # ── Execution ──────────────────────────────────────────────────────────
    agent_result: AgentResult | None
    subtask_results: list[AgentResult]
    pending_confirmation: bool

    # ── Conversation history ───────────────────────────────────────────────
    messages: list[dict]          # rolling window of completed turns (user+assistant pairs)
    last_active_at: float | None  # unix timestamp of last processed message

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
```

### Key invariants

- `prompt` may be empty on entry when `audio_data` is set — the `preprocess` node
  populates it from the transcription result before routing.
- `envelope.subtasks` always has at least one entry (enforced by `EmbeddingRouter`).
- `agent_context` is populated by `fetch_context` before any execution node runs.
- `messages` holds at most `SESSION_HISTORY_LIMIT` completed turns (10 by default).
  Image turns are stored as `"[Image] <caption>"` — raw bytes are never persisted
  in state.
- `pending_confirmation` is `True` between `draft_response` and the user's
  callback; it is reset to `False` by `await_confirmation`.

---

## Graph

`ze_core/orchestration/graph.py`

Ze Core splits graph construction into two functions so applications can add nodes
and custom routing without forking the entire graph module.

### `graph_builder()`

Returns a fully-wired but **uncompiled** `StateGraph(AgentState)` with:

- All standard nodes: `preprocess`, `embed_route`, `decompose`, `fetch_context`,
  `capability_check`, `execute_tool`, `draft_response`, `await_confirmation`,
  `synthesize`, `write_memory`.
- Entry point `preprocess`, with a fixed edge `preprocess → embed_route`.
- All internal edges **except** the `embed_route` conditional.

The `embed_route` conditional is **intentionally omitted** so callers can wire
custom destinations (e.g. Ze's `plan_sequential` node) before compile.

```python
def graph_builder() -> StateGraph:
    builder = StateGraph(AgentState)
    # ... add standard nodes and non-routing edges ...
    # embed_route conditional NOT added here
    return builder
```

### `build_graph(checkpointer)`

Default Ze Core topology for applications that do not extend the graph:

```python
def build_graph(checkpointer: AsyncPostgresSaver) -> CompiledGraph:
    from ze_core.orchestration.edges import after_embed_route

    builder = graph_builder()
    builder.add_conditional_edges(
        "embed_route",
        after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context"},
    )
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
```

Ze Core callers that use `Container.from_config()` receive this compiled graph
unless the application overrides graph construction.

### Extending the graph (Ze example)

Ze adds a `plan_sequential` node for the workflow agent and a third branch from
`embed_route`. The application imports `graph_builder` from ze-core, adds nodes,
wires routing, then compiles:

```python
from ze_core.orchestration.graph import graph_builder

def build_graph(checkpointer):
    from ze.orchestration import edges
    from ze.orchestration.nodes import routing

    builder = graph_builder()
    builder.add_node("plan_sequential", routing.plan_sequential)
    builder.add_conditional_edges(
        "embed_route",
        edges.after_embed_route,
        {
            "decompose": "decompose",
            "fetch_context": "fetch_context",
            "plan_sequential": "plan_sequential",
        },
    )
    builder.add_edge("plan_sequential", END)
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
```

Ze-specific nodes and edges live in `packages/ze/ze/orchestration/`; ze-core
remains the shared skeleton.

### Checkpoint interrupt

The `interrupt_before=["await_confirmation"]` configuration causes LangGraph to
checkpoint state before entering `await_confirmation` and pause the graph run.
The graph is resumed by calling `graph.ainvoke(None, config)` with the same
`thread_id` after the user responds (or via `Container.resume()` when using the
container API).

---

## Node Descriptions

All nodes are in `ze_core/orchestration/nodes/`.

### `preprocess`

Normalises multimodal input before routing. All LLM pre-processing happens here so
that downstream nodes always receive a populated `prompt` and never deal with raw bytes.

- **Audio** (`audio_data` set): calls `openrouter_client.transcribe()` with the model
  from `settings.config["models"]["whisper"]` (default `"openai/whisper-1"`). Writes
  `prompt = transcript`, `input_modality = "voice"`, clears `audio_data`/`audio_mime`
  so bytes are not persisted in the LangGraph checkpoint.
- **Image without prompt**: calls a cheap vision model to generate a one-sentence routing
  caption. Writes `image_caption`; `image_data` is preserved for the execution node.
  Model from `settings.config["models"]["vision_caption"]` (default `"google/gemini-flash-1.5"`).
- **Image with prompt**: sets `image_caption = prompt` (user's text serves as the caption).
- **Text-only**: no-op pass-through.

```python
async def preprocess(state: AgentState, config: RunnableConfig) -> dict: ...
```

### `embed_route`

Calls `EmbeddingRouter.route()` to produce a `RoutingEnvelope`. `preprocess` guarantees
that either `prompt` or `image_caption` is set before this node runs. Routing text is
`image_caption or prompt`.

```python
async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    router: EmbeddingRouter = config["configurable"]["router"]
    routing_text = state.get("image_caption") or state["prompt"]
    envelope = await router.route(prompt=routing_text, session_id=state["session_id"])
    return {"envelope": envelope}
```

### `decompose`

No-op passthrough for compound tasks. The `EmbeddingRouter` already called
`haiku_fallback.decompose()` internally; the `RoutingEnvelope` already contains all
subtasks. This node exists to keep the graph topology readable.

```python
async def decompose(state: AgentState, config: RunnableConfig) -> dict:
    return {}
```

### `fetch_context`

Encodes the prompt (or image caption) into an embedding, retrieves `MemoryContext`
from `MemoryStore`, loads the active persona, builds rolling message history, and
constructs an `AgentContext` that is passed to the executing agent.

```python
async def fetch_context(state: AgentState, config: RunnableConfig) -> dict:
    ...
    return {"memory_context": ..., "agent_context": ..., "last_active_at": now}
```

**Session expiry**: If `last_active_at` is set and the elapsed time exceeds
`settings.session_inactivity_minutes * 60` seconds, the message history is reset
to an empty list. This prevents stale context from bleeding across long gaps.

**Contacts**: If `person_store` is present in `config["configurable"]`, the node
also queries `PersonStore.get_context(prompt)` and attaches the result to
`AgentContext.contacts`. This is optional — applications that do not wire a
`PersonStore` simply get an empty `PersonContext`.

### `capability_check`

Calls `CapabilityGate.evaluate()` for the primary subtask (`envelope.subtasks[0]`).
Writes `gate_decision` to state.

```python
async def capability_check(state: AgentState, config: RunnableConfig) -> dict:
    gate: CapabilityGate = config["configurable"]["capability_gate"]
    primary = state["envelope"].subtasks[0]
    decision = gate.evaluate(primary.agent, primary.intent, state.get("session_overrides", {}))
    return {"gate_decision": decision}
```

If `envelope.subtasks` is empty (which must not happen — see routing spec), returns
`GateDecision.BLOCKED`.

### `execute_tool`

Runs the agent(s) named in `envelope.subtasks`. For single tasks, runs one agent.
For compound non-sequential tasks, runs all agents concurrently via `asyncio.gather`.
For compound sequential tasks, runs them one at a time, feeding each result into the
next context.

Each agent run is wrapped in `asyncio.wait_for` using `agent_cls.timeout` seconds.
A timeout raises `AgentTimeoutError`.

The resolved agent instance is retrieved via `get_agent(subtask.agent)` from the
agent instance registry (populated by `bootstrap_agents()` or equivalent DI wiring).

```python
async def execute_tool(state: AgentState, config: RunnableConfig) -> dict:
    ...
    # Single task → agent_result, subtask_results=[]
    # Compound    → agent_result=None, subtask_results=[...]
```

Timeout reads from `agent_cls.timeout` (class attribute), not from YAML.

### `draft_response`

Identical to `execute_tool` but builds an `AgentContext` with
`gate_decision=GateDecision.DRAFT`. The agent receives a draft gate decision and
must suppress any write-side-effect tool calls internally. Returns
`{"agent_result": result, "pending_confirmation": True}`.

### `await_confirmation`

The confirmation resume point. The graph is interrupted *before* this node by
`interrupt_before`. When the transport adapter resumes the graph (after the user
responds), this node runs and resets the gate decision to `EXECUTE` so the
downstream `execute_tool` performs the real write.

```python
async def await_confirmation(state: AgentState, config: RunnableConfig) -> dict:
    return {"pending_confirmation": False, "gate_decision": GateDecision.EXECUTE}
```

The transport adapter is responsible for:
1. Reading `state["agent_result"].response` to present the draft to the user.
2. Collecting the user's decision (approved / rejected).
3. If approved: calling `graph.ainvoke(None, config)` with the same `thread_id`.
4. If rejected: discarding — the graph is never resumed; the paused checkpoint
   remains but is never replayed.

`await_confirmation` does not call `AppInterface` methods. The transport adapter
handles all user interaction outside the graph. This keeps the graph transport-agnostic.

### `synthesize`

Merges multiple `subtask_results` into a single coherent response by calling a
synthesis model (default: `"anthropic/claude-haiku-4-5"`). The synthesis model is
read from `settings.config["models"]["synthesis"]`.

Only runs when `envelope.is_compound and not envelope.is_sequential`. Sequential
compound tasks do not synthesize — the final subtask's response is the answer.

```python
async def synthesize(state: AgentState, config: RunnableConfig) -> dict:
    ...
    return {"final_response": synthesized_text}
```

### `write_memory`

Fires background tasks (`asyncio.create_task`) to persist the episode and any
proposed facts from the agent result. Also appends the completed turn to the
rolling `messages` history (trimmed to `SESSION_HISTORY_LIMIT`).

Write failures are swallowed — never propagated. Memory writes must not fail the
graph.

Skips writes when `thread_id` starts with `"eval-"` (evaluation runs must not
pollute production memory).

```python
async def write_memory(state: AgentState, config: RunnableConfig) -> dict:
    ...
    return {"messages": updated[-SESSION_HISTORY_LIMIT:]}
```

---

## Conditional Edges

`ze_core/orchestration/edges.py`

### `after_embed_route`

```python
def after_embed_route(state: AgentState) -> str:
    envelope = state["envelope"]
    if envelope.is_compound:
        return "decompose"
    return "fetch_context"
```

In the **default** Ze Core graph, compound tasks (parallel and sequential) go to
`decompose` first; sequential execution is handled inside `execute_tool`.

Ze's extended graph replaces `after_embed_route` with a version that can return
`plan_sequential` for sequential compound workflow tasks (see Graph → Extending the
graph above). That node is not part of ze-core's `build_graph()`.

### `after_capability_check`

```python
def after_capability_check(state: AgentState) -> str:
    match state["gate_decision"]:
        case GateDecision.EXECUTE:
            return "execute_tool"
        case GateDecision.DRAFT | GateDecision.AWAIT_CONFIRMATION:
            return "draft_response"
        case GateDecision.BLOCKED | _:
            return "end_blocked"
```

Both `DRAFT` and `AWAIT_CONFIRMATION` go to `draft_response`. The gate decision is
preserved in state — `draft_response` reads it to know whether to also set
`pending_confirmation=True`.

### `after_execute_tool`

```python
def after_execute_tool(state: AgentState) -> str:
    envelope = state["envelope"]
    if envelope.is_compound and state.get("subtask_results"):
        return "synthesize"
    return "write_memory"
```

---

## Configurable Dependencies

All dependencies are injected through `config["configurable"]` at invocation time,
not at graph build time. The graph is stateless — it can be shared safely across
concurrent invocations.

| Key | Type | Required | Purpose |
|---|---|---|---|
| `router` | `EmbeddingRouter` | Yes | `embed_route` node |
| `capability_gate` | `CapabilityGate` | Yes | `capability_check` node |
| `memory_store` | `MemoryStore` | Yes | `fetch_context`, `write_memory` |
| `embedder` | `SentenceTransformer` | Yes | `fetch_context`, `write_memory` |
| `openrouter_client` | `OpenRouterClient` | Yes | `preprocess` (transcription + caption), `synthesize` |
| `settings` | `Settings` | Yes | timeouts, models, session expiry |
| `thread_id` | `str` | Yes | LangGraph checkpoint key; `"eval-"` prefix skips memory |
| `persona_store` | `PersonaStore` | No | `fetch_context` — active persona |
| `person_store` | `PersonStore` | No | `fetch_context` — contact context |
| `contact_channel_store` | `ContactChannelStore` | No | `write_memory` — contact handle writes |
| `reporter` | `ProgressReporter` | No | `execute_tool` — in-flight status updates |
| `token_queue` | `asyncio.Queue` | No | `execute_tool` — streaming tokens to transport |

All optional keys are accessed via `config["configurable"].get(key)`. Their
absence is handled gracefully — the node skips the feature rather than raising.

---

## Invocation Contract

### Starting a new turn

```python
config = {
    "configurable": {
        "thread_id": session_id,
        "router": router,
        "capability_gate": gate,
        "memory_store": memory_store,
        "embedder": embedder,
        "openrouter_client": client,
        "settings": settings,
        # optional:
        "persona_store": persona_store,
        "person_store": person_store,
    }
}
state = {
    "prompt": user_message,   # empty string when audio_data is set
    "session_id": session_id,
    "session_overrides": {},
    "input_modality": "text",  # "voice" when audio_data set; "image" when image_data set
    "audio_data": None,        # raw audio bytes; preprocess node transcribes and clears
    "audio_mime": None,
    "image_data": None,
    "image_mime": None,
    "image_caption": None,
}
result = await graph.ainvoke(state, config)
```

### Resuming after confirmation

```python
result = await graph.ainvoke(None, config)
```

The same `config` (with the same `thread_id`) is used. LangGraph restores state
from the checkpoint and resumes from `await_confirmation`.

---

## Graph Topology Diagram

```
preprocess   (transcription / vision caption)
    │
embed_route
    │
    ├─ is_compound ─→ decompose ─→ fetch_context
    │                                   │
    └─ single ──────────────────→ fetch_context
                                        │
                                  capability_check
                                        │
                        ┌───────────────┼───────────────┐
                        │               │               │
                   EXECUTE         DRAFT/CONFIRM     BLOCKED
                        │               │               │
                  execute_tool    draft_response      END
                        │               │
                        │        await_confirmation
                        │               │ (resumes here after user confirm)
                        └───────────────┘
                                        │
                    ┌───────────────────┴────────────────┐
                    │                                     │
              is_compound=True                   is_compound=False
                    │                                     │
                synthesize                          write_memory
                    │                                     │
              write_memory                             END
                    │
                   END
```

---

## Session History

`messages` in `AgentState` is the rolling conversation history. It is persisted in
the LangGraph checkpoint and survives restarts.

- Limit: `SESSION_HISTORY_LIMIT = 10` entries (5 turns: user + assistant × 5).
- Format: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`
- Image turns: user content is stored as `"[Image] <caption>"` — base64 bytes are
  never written to the checkpoint.
- Expiry: if `last_active_at` is older than `settings.session_inactivity_minutes`
  minutes, `fetch_context` clears the history for the current turn.

---

## Error Handling

| Condition | Behaviour |
|---|---|
| `preprocess` receives audio but no transcription model configured | `OpenRouterError` propagates — graph aborts |
| `embed_route` receives empty prompt and no image_caption | `EmbeddingRouter` raises `InvalidPromptError` — graph aborts |
| `capability_check` gets no envelope subtasks | Returns `GateDecision.BLOCKED` — routes to END |
| `execute_tool` agent times out | `AgentTimeoutError` — graph writes error episode and ends |
| `execute_tool` agent raises unexpectedly | Exception propagates; LangGraph surfaces it to the caller |
| `write_memory` background task fails | Swallowed — logged as warning; graph returns normally |
| `synthesize` LLM call fails | Exception propagates — handled by the transport caller |
| Vision caption call fails | Exception propagates from `embed_route` — turn fails |

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `ze_core.orchestration.state` | `AgentState` |
| `ze_core.routing.router` | `EmbeddingRouter` |
| `ze_core.capability.gate` | `CapabilityGate` |
| `ze_core.orchestration.registry` | `get_agent()` — retrieve live agent instance |
| `ze_core.routing.types` | `RoutingEnvelope`, `SubTask` |
| `ze_core.agents.types` | `AgentContext`, `AgentResult` |
| `ze_core.capability.types` | `GateDecision` |
| `ze_core.memory.store` | `MemoryStore` |
| `ze_core.errors` | `AgentTimeoutError`, `InvalidPromptError` |
| `ze_core.logging` | Structured logging |
| `langgraph` | `StateGraph`, `AsyncPostgresSaver`, `interrupt_before` |
