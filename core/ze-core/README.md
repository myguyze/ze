# ze-core

LangGraph orchestration engine for Ze. Pure infrastructure — routing, graph execution, capability gate, OpenRouter client, telemetry, and DI container. Contains no personal-assistant domain logic.

## Role in Ze

Every user message flows through the LangGraph built by `ze-core`. The graph handles routing, context retrieval, capability checks, agent execution, memory writes, and response synthesis. `ze-core` is the engine layer — it knows how to orchestrate agents but not what those agents do.

### Key features

- Embedding-based intent routing with complexity estimation and compound-query decomposition
- LangGraph state machine with confirmation pauses, multimodal preprocessing, and checkpoint persistence
- Capability gate — per-agent permission modes with Postgres-backed overrides
- Cost telemetry — per-flow and per-agent token tracking with automatic reconciliation
- OpenRouter client — all LLM, transcription, and vision calls go through a single gateway

### Integration

`ze-api` instantiates `ZeContainer` (subclass of `ze_core.container.Container`), builds the graph via `graph_builder`, and injects dependencies at invocation time. Plugins extend the graph through `ZePlugin` hooks in `ze-plugin` — `ze-core` merges their nodes, state fields, and configurable services at build time. Not imported directly from plugin packages.

## Responsibilities

| Module | What it provides |
|---|---|
| `orchestration/` | `graph_builder`, `AgentState`, graph nodes and edges |
| `routing/` | `EmbeddingRouter`, `ComplexityEstimator`, `PostgresRoutingStore`, fallback |
| `capability/` | `CapabilityGate`, `PostgresCapabilityOverrideStore`, permission modes |
| `openrouter/` | `OpenRouterClient`, streaming, transcription |
| `telemetry/` | `CostTracker`, `CostReconciler`, `PostgresCostStore`, context var |
| `conversation/` | Message/session/confirmation stores + graph turn helpers |
| `container.py` | Base `Container` with DI wiring |
| `embeddings.py` | Shared `paraphrase-multilingual-MiniLM-L12-v2` singleton |
| `checkpoint_serde.py` | LangGraph checkpoint serialisation for plugin types |

Agent execution (`BaseAgent`, `@agent`, `@tool`), plugin framework (`ZePlugin`, channels), and memory live in sibling packages — `ze-agents`, `ze-plugin`, and `ze-memory`.

## Dependencies

```mermaid
graph LR
    core[ze-core] --> agents[ze-agents]
    core --> plugin[ze-plugin]
```

Third-party: `langgraph`, `openrouter`, `numpy`, `structlog`.

## Usage

Consumed by `ze-api` and never imported directly from plugin packages:

```python
from ze_core.orchestration.graph import graph_builder
from ze_core.container import Container
from ze_core.routing.router import EmbeddingRouter
```

## Testing

From the repo root:

```bash
make test-core
```

Pass `SLOW=1` to include embedding model tests. See [docs/testing.md](../../docs/testing.md).
