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
- Compile and expose the LangGraph graph in `ze_core/orchestration/graph.py`.
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
    image_data: bytes | None    # raw image bytes; None for text/voice turns
    image_mime: str | None      # "image/jpeg" | "image/png" | None
    image_caption: str | None   # caption generated at embed_route; None until set

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

- `prompt` is never empty when the graph starts (validated at entry by the
  transport adapter before invoking the graph).
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

```python
def build_graph(checkpointer: AsyncPostgresSaver) -> CompiledGraph:
    builder = StateGraph(AgentState)

    builder.add_node("embed_route",        nodes.embed_route)
    builder.add_node("decompose",          nodes.decompose)
    builder.add_node("fetch_context",      nodes.fetch_context)
    builder.add_node("capability_check",   nodes.capability_check)
    builder.add_node("execute_tool",       nodes.execute_tool)
    builder.add_node("draft_response",     nodes.draft_response)
    builder.add_node("await_confirmation", nodes.await_confirmation)
    builder.add_node("synthesize",         nodes.synthesize)
    builder.add_node("write_memory",       nodes.write_memory)

    builder.set_entry_point("embed_route")

    builder.add_conditional_edges(
        "embed_route",
        edges.after_embed_route,
        {"decompose": "decompose", "fetch_context": "fetch_context"},
    )
    builder.add_edge("decompose", "fetch_context")
    builder.add_edge("fetch_context", "capability_check")
    builder.add_conditional_edges(
        "capability_check",
        edges.after_capability_check,
        {"execute_tool": "execute_tool", "draft_response": "draft_response", "end_blocked": END},
    )
    builder.add_conditional_edges(
        "execute_tool",
        edges.after_execute_tool,
        {"synthesize": "synthesize", "write_memory": "write_memory"},
    )
    builder.add_edge("draft_response",     "await_confirmation")
    builder.add_edge("await_confirmation", "execute_tool")
    builder.add_edge("synthesize",         "write_memory")
    builder.add_edge("write_memory",       END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
```

The `interrupt_before=["await_confirmation"]` configuration causes LangGraph to
checkpoint state before entering `await_confirmation` and pause the graph run.
The graph is resumed by calling `graph.ainvoke(None, config)` with the same
`thread_id` after the user responds.

---

## Node Descriptions

All nodes are in `ze_core/orchestration/nodes/`.

### `embed_route`

Calls `EmbeddingRouter.route()` to produce a `RoutingEnvelope`. For image turns
without a text prompt, first calls a cheap vision model to generate a one-sentence
routing caption, then routes on that caption. Writes `envelope` (and optionally
`image_caption`) to state.

```python
async def embed_route(state: AgentState, config: RunnableConfig) -> dict:
    router: EmbeddingRouter = config["configurable"]["router"]
    ...
    envelope = await router.route(prompt=routing_text, session_id=state["session_id"])
    return {"envelope": envelope, ...}
```

The vision caption model is read from `settings.config["models"]["vision_caption"]`.
Default: `"google/gemini-flash-1.5"`. The `OpenRouterClient` must be present in
`config["configurable"]` whenever `input_modality == "image"` and `prompt` is empty.

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

Compound tasks (both parallel and sequential) go to `decompose` first. Sequential
compound tasks are handled inside `execute_tool` — there is no separate sequential
planning node in Ze Core. (Ze's `plan_sequential` node is a Ze-specific extension
for the workflow agent and is not part of the Ze Core graph.)

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
| `openrouter_client` | `OpenRouterClient` | Yes | `synthesize`, vision caption |
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
    "prompt": user_message,
    "session_id": session_id,
    "session_overrides": {},
    "input_modality": "text",
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
| `embed_route` receives empty prompt | `EmbeddingRouter` raises `InvalidPromptError` — graph aborts |
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
