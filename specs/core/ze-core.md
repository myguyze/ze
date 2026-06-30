# ze-core — Orchestration Engine

> **Package:** `core/ze-core` — `ze_core/`
> **Status:** Done
> **Supersedes:** [01-agent.md](01-agent.md), [02-app-interface.md](02-app-interface.md), [03-capability-gate.md](03-capability-gate.md), [04-routing.md](04-routing.md), [05-orchestration.md](05-orchestration.md), [07-container.md](07-container.md), [09-conversation.md](09-conversation.md) (all stale)

The engine. Routes messages, builds and runs the LangGraph graph, manages
DI, wires plugins together. Plugin code never imports from `ze_core`.

---

## Purpose

Owns the full request lifecycle: receive a message → embed → route → check capability →
execute agent → write memory → send response. Manages the LangGraph graph with
`AsyncPostgresSaver` checkpoints, the DI container, plugin discovery, and telemetry.

---

## Responsibilities

- **Routing** — `EmbeddingRouter` embeds the message, cosine-similarity matches to
  agent intents; `ComplexityEstimator` decides compound vs. single-agent; fallback
  to haiku-class on low-confidence
- **Capability gate** — `CapabilityGate` checks the current `Mode` against the matched
  agent; `PostgresCapabilityOverrideStore` persists per-agent overrides
- **Orchestration graph** — `graph_builder` compiles the LangGraph graph; nodes are
  `transcribe`, `embed_route`, `decompose`, `fetch_context`, `capability_check`,
  `execute_tool`, `synthesize`, `write_memory`, `draft_response`, `await_confirmation`,
  `record_trace`
- **Container** — `BaseContainer` wires all dependencies; `invoke_raw_turn` and `resume`
  are the entry points; plugins register via `startup(container)`
- **Telemetry** — `CostTracker` accumulates per-flow token usage; `CostReconciler`
  reconciles against OpenRouter invoices; `PostgresCostStore` persists
- **Conversation** — `MessageStore` persists messages; `PendingConfirmationStore`
  persists paused confirmation requests for replay after restart
- **NLI** — `NLIClient` singleton (`cross-encoder/nli-deberta-v3-small`) shared across
  memory and correlation
- **Embeddings** — `paraphrase-multilingual-MiniLM-L12-v2` singleton used by router and
  memory; loaded once at startup

---

## Out of Scope

- Agent logic and tool execution — `ze-agents`
- Plugin definitions and ZePlugin ABC — `ze-plugin`
- Domain features (contacts, goals, calendar) — plugin packages
- Public plugin API — `ze-sdk`

---

## Module Location

```
core/ze-core/ze_core/
  orchestration/      ← graph_builder, nodes, AgentState, edges, agent registry
  routing/            ← EmbeddingRouter, ComplexityEstimator, fallback, RouterStore
  capability/         ← CapabilityGate, PostgresCapabilityOverrideStore, Mode
  telemetry/          ← CostTracker, CostReconciler, PostgresCostStore, ContextVar
  openrouter/         ← OpenRouterClient (engine-internal; plugins use LLMClient Protocol)
  interface/          ← AppInterface wiring, InputPreprocessor
  conversation/       ← MessageStore, PendingConfirmationStore, SessionStore
  messages/           ← message types used in graph state
  container.py        ← BaseContainer — DI wiring, invoke_raw_turn, resume
  embeddings.py       ← embedding singleton (lru_cache)
  nli.py              ← NLIClient singleton
  checkpoint_serde.py ← LangGraph checkpoint type serialisers
  migrate.py          ← meta-runner entry (owned migrations only)
  migrations/         ← zc* chain (graph checkpoints, messages, sessions, confirmations)
```

---

## Key invariants

- `OpenRouterClient` is engine-internal. Plugins receive `LLMClient` (Protocol) via DI
  and never import `ze_core.openrouter` directly.
- The graph is compiled once at startup (`graph_builder(plugins)`). Adding a node
  requires a restart.
- `invoke_raw_turn` uses `graph.astream_events` (Phase 95+); prior to Phase 95 it used
  `graph.ainvoke`.
- Confirmation resume: `resume(thread_id, choice)` calls `graph.ainvoke(None, config)`
  with the same `thread_id` — the graph continues from the `await_confirmation` node.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `BaseAgent`, `AgentRegistry`, `AppInterface`, `LLMClient` |
| `ze-communication` | `ChannelRegistry` |
| `ze-plugin` | `ZePlugin`, plugin discovery |
| `ze-logging` | `get_logger` |

---

## Links

- [ADR — LangGraph Orchestration](../arch/langgraph-orchestration.md)
- [ADR — OpenRouter Gateway](../arch/openrouter-gateway.md)
- [ADR — Local Embeddings](../arch/local-embeddings.md)
