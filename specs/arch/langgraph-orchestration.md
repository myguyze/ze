# ADR: Use LangGraph + AsyncPostgresSaver for orchestration

> **Status:** Accepted
> **Date:** 2023-11-01 (Phase 5)
> **Scope:** `ze-core` orchestration graph — every message handled by the system

---

## Context and Problem Statement

Ze routes messages through a multi-step pipeline: embed → route → capability check →
agent execution → memory write → response. Some flows pause mid-execution waiting
for user confirmation. Restarts must resume where they left off. The question is what
execution substrate handles this.

---

## Decision Drivers

- Confirmation flows require pausing mid-graph and resuming later (possibly after a
  process restart)
- The graph structure is inspectable and testable in isolation
- Async throughout — every node does I/O
- Single user means the graph is never under concurrent write pressure from multiple users

---

## Considered Options

1. **Raw asyncio** — custom task queue + Redis for state
2. **Temporal / Prefect** — workflow engine with durable execution
3. **LangGraph with in-memory state** — graph execution but no persistence
4. **LangGraph + AsyncPostgresSaver** — graph execution with Postgres-backed checkpoints

---

## Decision Outcome

**Chosen option: LangGraph + AsyncPostgresSaver.**

LangGraph's graph model maps cleanly onto Ze's pipeline. `AsyncPostgresSaver`
makes graph state durable without a separate workflow engine. The confirmation pause
(`await_confirmation` node) is implemented as a graph interrupt that resumes via
`graph.ainvoke(None, config)` with the same `thread_id` — no bespoke state machine.

### Positive Consequences

- Graph pauses and resumes across process restarts without custom serialisation
- Graph structure is explicit code, not implicit task wiring
- Each node is independently testable
- LangGraph's `astream_events` gives node-level observability (Phase 95)

### Negative Consequences / Trade-offs

- LangGraph's API surface is large and updates are occasionally breaking
- `AsyncPostgresSaver` schema is LangGraph-internal — migrating off would require
  a checkpoint export step
- Graph compilation happens at startup; adding nodes requires a restart
- Debugging async graph execution is harder than a linear pipeline

---

## Pros and Cons of the Options

### Option 1 — Raw asyncio

**Pros:** No framework dependency, full control.

**Cons:** Confirmation flows need a hand-rolled state machine; durable mid-execution
pause is complex to implement correctly.

### Option 2 — Temporal / Prefect

**Pros:** Battle-tested durable execution, rich UI, retry policies.

**Cons:** Significant ops overhead (Temporal server); overkill for single-user
low-concurrency assistant; adds an external dependency with its own upgrade cycle.

### Option 3 — LangGraph in-memory

**Pros:** Simple, no persistence layer.

**Cons:** Process restart loses in-flight graph state; confirmation flows can't
survive restarts.

### Option 4 — LangGraph + AsyncPostgresSaver

**Pros:** Durable, graph-native, async, no extra infrastructure beyond the Postgres
already required.

**Cons:** See negative consequences above.

---

## Links

- [Phase 5 — Orchestration](../phases/05-orchestration.md)
- [core/05-orchestration.md](../core/05-orchestration.md)
- `core/ze-core/ze_core/orchestration/` — graph builder, nodes, `AgentState`
