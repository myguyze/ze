# Orchestration — Spec

## Purpose

Define the LangGraph state machine that coordinates routing, capability checking,
memory injection, agent execution, and response synthesis. This is the central
nervous system of Ze — it owns the execution flow and nothing else. Individual
nodes are thin wrappers that delegate to domain modules.

## Responsibilities

- Define `AgentState` as the single source of truth for graph state.
- Define all graph nodes as pure async functions in `nodes/`.
- Define all conditional edges as pure functions in `edges.py`.
- Compile and expose the LangGraph graph in `graph.py`.
- Persist graph state via `AsyncPostgresSaver` (survives restarts).
- Support parallel branch execution for compound tasks via LangGraph `Send` API.
- Handle human-in-the-loop pausing for confirmation via `interrupt_before`.
- Enforce per-agent node timeouts via `asyncio.wait_for`.
- Stream partial responses to the WebSocket layer as tokens arrive.

## Out of Scope

- Does not implement agent logic (delegates to `ze/agents/`).
- Does not implement capability evaluation (delegates to `ze/capability/gate.py`).
- Does not implement memory storage (delegates to `ze/memory/store.py`).
- Does not manage WebSocket connections (delegates to `ze/api/ws.py`).

## State Definition

`ze/orchestration/state.py`

```python
from typing import TypedDict
from ze.routing.types import RoutingEnvelope
from ze.agents.types import AgentResult, AgentContext
from ze.capability.types import GateDecision
from ze.memory.types import MemoryContext

class AgentState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    prompt: str
    session_id: str
    session_overrides: dict[str, str]   # agent.intent → mode string

    # ── Routing ────────────────────────────────────────────────────────────
    envelope: RoutingEnvelope | None

    # ── Context ────────────────────────────────────────────────────────────
    memory_context: MemoryContext | None
    agent_context: AgentContext | None

    # ── Capability ─────────────────────────────────────────────────────────
    gate_decision: GateDecision | None

    # ── Execution ──────────────────────────────────────────────────────────
    agent_result: AgentResult | None
    subtask_results: list[AgentResult]  # populated during compound task fan-out
    pending_confirmation: bool

    # ── Conversation history ────────────────────────────────────────────────
    messages: list[dict]
    last_active_at: float | None

    # ── Workflow execution (None / 0 / [] in normal graph runs) ────────────
    workflow_id: UUID | None
    workflow_execution_id: UUID | None
    workflow_steps: list | None          # list[WorkflowStep]
    current_step_index: int
    workflow_step_results: list          # list[StepResult]

    # ── Output ─────────────────────────────────────────────────────────────
    final_response: str | None
    error: str | None
```

`AgentState` must be JSON-serialisable. All contained types must implement
`__dict__`-compatible serialisation. The `AsyncPostgresSaver` checkpointer
serialises the full state dict between graph pauses.

## Graph Nodes

Defined across files in `ze/orchestration/nodes/`.

### `nodes/routing.py`

| Node | Input state keys | Output state keys |
|------|-----------------|-------------------|
| `embed_route` | `prompt`, `session_id` | `envelope` |
| `decompose` | `envelope`, `prompt` | `envelope` (subtasks populated) |

- `embed_route` calls `EmbeddingRouter.route()`.
- `decompose` calls `haiku_fallback.decompose()`. Only reached when
  `envelope.is_compound is True` after initial routing.

### `nodes/context.py`

| Node | Input state keys | Output state keys |
|------|-----------------|-------------------|
| `fetch_context` | `envelope`, `prompt` | `memory_context`, `agent_context` |

- Encodes the prompt and calls `MemoryStore.get_context()`.
- Builds `AgentContext` from `envelope` + `memory_context`.

### `nodes/execution.py`

| Node | Input state keys | Output state keys |
|------|-----------------|-------------------|
| `capability_check` | `envelope`, `session_overrides` | `gate_decision` |
| `execute_tool` | `agent_context`, `gate_decision` | `agent_result` |
| `draft_response` | `agent_context` | `agent_result` (draft mode) |

- `capability_check` calls `CapabilityGate.evaluate()`.
- `execute_tool` calls `agent_registry.get_agent(name).run(context)` wrapped in
  `asyncio.wait_for(timeout=agent_config.timeout_seconds)`.
- `draft_response` runs the agent but suppresses any tool calls that would cause
  writes. Returns `AgentResult.draft_content` populated.

### `nodes/confirmation.py`

| Node | Input state keys | Output state keys |
|------|-----------------|-------------------|
| `await_confirmation` | `agent_result` | `pending_confirmation` |

- Sets `pending_confirmation=True` and emits a `confirmation_request` WebSocket
  message to the client.
- Graph is paused here via `interrupt_before`. The `AsyncPostgresSaver` checkpoints
  state. Execution resumes when the WebSocket handler receives a `confirm` message.

### `nodes/memory.py`

| Node | Input state keys | Output state keys |
|------|-----------------|-------------------|
| `write_memory` | `agent_result`, `agent_context` | _(no state mutation)_ |
| `synthesize` | `subtask_results` | `final_response` |

- `write_memory` always runs, even if `error` is set. It fires
  `MemoryStore.write_episode()` and `MemoryStore.propose_facts()` as
  `asyncio.create_task` — non-blocking.
- On error: writes an episode with `response="[ERROR] {error}"` and empty
  `memory_proposals`.
- `synthesize` merges multiple `AgentResult.output` strings into a single
  coherent response via Haiku. Only reached when `subtask_results` is non-empty.

## Conditional Edges

`ze/orchestration/edges.py` — all pure functions, no side effects.

```python
def after_embed_route(state: AgentState) -> str:
    if state["envelope"].is_compound:
        return "decompose"
    return "fetch_context"

def after_capability_check(state: AgentState) -> str:
    decision = state["gate_decision"]
    match decision:
        case GateDecision.EXECUTE:            return "execute_tool"
        case GateDecision.DRAFT:              return "draft_response"
        case GateDecision.AWAIT_CONFIRMATION: return "await_confirmation"
        case GateDecision.BLOCKED:            return "end_blocked"

def after_execute_tool(state: AgentState) -> str:
    if state["subtask_results"]:
        return "synthesize"
    return "write_memory"
```

## Graph Assembly

`ze/orchestration/graph.py`

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

def build_graph(checkpointer: AsyncPostgresSaver) -> CompiledGraph:
    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node("embed_route",          nodes.routing.embed_route)
    builder.add_node("decompose",            nodes.routing.decompose)
    builder.add_node("fetch_context",        nodes.context.fetch_context)
    builder.add_node("capability_check",     nodes.execution.capability_check)
    builder.add_node("execute_tool",         nodes.execution.execute_tool)
    builder.add_node("draft_response",       nodes.execution.draft_response)
    builder.add_node("await_confirmation",   nodes.confirmation.await_confirmation)
    builder.add_node("synthesize",           nodes.memory.synthesize)
    builder.add_node("write_memory",         nodes.memory.write_memory)

    # Entry point
    builder.set_entry_point("embed_route")

    # Edges
    builder.add_conditional_edges("embed_route", edges.after_embed_route)
    builder.add_edge("decompose", "fetch_context")
    builder.add_edge("fetch_context", "capability_check")
    builder.add_conditional_edges("capability_check", edges.after_capability_check)
    builder.add_conditional_edges("execute_tool", edges.after_execute_tool)
    builder.add_edge("draft_response", "await_confirmation")
    builder.add_edge("await_confirmation", END)       # graph pauses here
    builder.add_edge("synthesize", "write_memory")
    builder.add_edge("write_memory", END)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["await_confirmation"],
    )
```

## Compound Task Fan-out

For compound tasks, LangGraph's `Send` API fans out one graph invocation per
subtask. Each subtask branch runs `fetch_context → capability_check → execute_tool`
in parallel. Results accumulate in `subtask_results`. The `synthesize` node merges
them.

This is implemented in `nodes/routing.py`'s `decompose` node by returning a list
of `Send` objects — one per `SubTask` in the envelope.

## Node Timeouts

Every `execute_tool` and `draft_response` call is wrapped:

```python
try:
    result = await asyncio.wait_for(
        agent.run(context),
        timeout=agent_config.timeout_seconds,
    )
except asyncio.TimeoutError:
    raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")
```

Timeout values come from `config/agents/<name>.yaml` (`timeout_seconds`).
`AgentTimeoutError` extends `AgentError` from `ze/errors.py`.

## Checkpointer Setup

`AsyncPostgresSaver` is initialised in `ze/api/app.py` during the FastAPI lifespan
using the shared asyncpg pool. LangGraph creates its own checkpoint tables on first
use (see migration `002_checkpointer.py`).

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def lifespan(app: FastAPI):
    pool = await create_pool(settings.database_url)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()   # creates LangGraph tables if not exist
    app.state.graph = build_graph(checkpointer)
    yield
    await pool.close()
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `langgraph` | Graph engine, `StateGraph`, `Send`, `interrupt_before` |
| `langgraph-checkpoint-postgres` | `AsyncPostgresSaver` |
| `ze.routing.router` | `EmbeddingRouter` |
| `ze.routing.haiku_fallback` | Decomposition |
| `ze.agents.registry` | `get_agent()` |
| `ze.capability.gate` | `CapabilityGate` |
| `ze.memory.store` | `MemoryStore` |
| `ze.errors` | `AgentTimeoutError`, `AgentError` |
| `ze.settings` | Config access |

## Workflow Graph (Phase 4)

A second compiled graph (`ze/orchestration/workflow_graph.py`) handles sequential
workflow execution. It reuses the same node functions as the main graph but has a
different topology that loops through steps.

**Entry point:** `load_workflow_step` (not `embed_route`)

**Loop:** `load_workflow_step → embed_route → fetch_context → capability_check →
execute_tool → write_memory → verify_step → [loop | workflow_synthesize | workflow_failed]`

**Key differences from the main graph:**
- No `decompose`, `draft_response`, `await_confirmation`, or `synthesize` nodes.
- `after_capability_check_workflow` maps all non-BLOCKED decisions to `execute_tool`
  (workflow steps execute directly — workflow creation was the gate).
- `verify_step` does programmatic output validation and advances `current_step_index`.
- `thread_id` is set to `str(workflow_execution_id)`, not the Telegram chat ID.

See `12-workflow.md` for the full workflow system spec.

## Open Questions

All resolved.
