# Inline Conversational Correlation — Spec

> **Package:** `ze-correlation` (consumer), `ze-core` (orchestration node), `ze-components`, `ze-web`
> **Phase:** 58
> **Status:** Pending — **v1 scope** (sole user-visible correlation consumer until Phase 59)
> **Depends on:** Correlation Engine ([57-correlation-engine.md](57-correlation-engine.md)), Salience Model ([56-salience-relevance-model.md](56-salience-relevance-model.md)), Signal Substrate ([55-signal-substrate.md](55-signal-substrate.md)), Orchestration ([../core/05-orchestration.md](../core/05-orchestration.md)), Component Descriptors ([41-component-descriptors.md](41-component-descriptors.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| Correlation graph node | 🔲 Pending |
| `AgentState` extension | 🔲 Pending |
| Response "connections" section | 🔲 Pending |
| Web rendering component | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

When the user asks about a topic in a normal turn, Ze should recall related prior signals
and surface the connection **right there in the answer**, in a dedicated section. Asking
"what's the news on Anthropic?" should, if Ze holds the earlier defence-deal signal,
return the headlines *and* a "connections" section noting the prior event and the possible
link.

This is the **v1 user-visible consumer** of the correlation engine (Phase 57). The
proactive push (Phase 59) is explicitly deferred — v1 ships inline-only. Inline sidesteps
the hardest problem (deciding unprompted when to interrupt) and earns trust with a built-in
feedback loop before autonomous pushes are enabled.

---

## Responsibilities

- During a qualifying turn, derive seed entities/topics from the turn and call
  `CorrelationEngine.correlate(seeds, mode="inline")`.
- Apply the **inline bar** (Phase 56): recall guarantee + low confidence floor; no novelty
  or budget gating.
- Inject qualifying hypotheses into `AgentState` so synthesis renders a clearly-labelled,
  evidence-cited "connections" section, visually distinct from the main answer.
- Respect a strict latency budget: if correlation does not return in time, the turn
  proceeds without a connections section. Correlation must never delay or break the answer.
- Make provenance visible: the answer body may be live (the agent searched the news), but
  the connection is recalled history — the UI must not blur the two.

---

## Out of Scope

- The proactive push consumer (Phase 59) and its interrupt bar.
- Signal admission / relevance set construction (Phase 56) and anchoring (Phase 55).
- Multi-signal convergence (Phase 61).
- Live search inside correlation — v1 is recall-only (Phase 57).

---

## Where it hooks

```
fetch_context → capability_check → execute_tool → correlate → synthesize → write_memory → END
```

- `correlate` reads the turn's resolved entities and calls the engine with a tight budget,
  writes results into `AgentState`.
- `synthesize` appends a connections section when present.
- Placed as a graph node (not an agent tool) so it is deterministic and uniformly gated.

---

## Data Structures

```python
class CorrelationStateExt(TypedDict, total=False):
    correlations: list[Hypothesis]      # Phase 57 type; inline-qualifying only
```

Rendering reuses `Hypothesis` via a server-driven component descriptor (Phase 41).

---

## Behaviour

### Seed selection

- Entities/topics from the current turn. Skip when no resolvable salient entity.

### Inline bar (Phase 56)

- Recall guarantee: ≥2 distinct `graph_recall` items.
- `correlation_confidence >= τ_inline` (low; `τ_inline < τ_push`).
- No novelty/budget gate.

### Rendering

- Distinct section below the main answer (e.g. "Connected to your history").
- Evidence shows provenance and dates. Main answer freshness vs recalled connection are
  visually separated.

### Latency

- Hard timeout (`inline_timeout_ms`). On timeout: drop section, log, proceed.
- Tighter neighbourhood bounds than proactive mode.

---

## Configuration

```yaml
correlation:
  inline:
    enabled: true
    tau_inline: 0.45
    inline_timeout_ms: 1500
    inline_max_hops: 1
    inline_limit: 15
    max_connections_shown: 2
    agents: ["research", "news"]
```

---

## Dependencies

| Dependency | Purpose |
| ---------- | ------- |
| `ze_correlation.CorrelationEngine` | `correlate(mode="inline")` |
| `ze_core.orchestration` | graph node + `AgentState` |
| `ze_memory` graph + relevance | neighbourhood + seeds |
| `ze_components` / `ze_web` | connections section rendering |

---

## Test Plan

- Turn "news on Anthropic" with a pre-seeded prior Pentagon signal yields a connections
  section citing both, evidence tagged `graph_recall`.
- No related prior signal → no connections section.
- Chit-chat / commands skip correlation.
- Latency timeout → answer ships without section.
- Provenance: `live_search`-only connections are not shown.
- Only configured agents trigger inline correlation.

---

## Open Questions

- [ ] **Node vs tool.** (Leaning node — deterministic and uniformly gated.)
- [ ] **Which turns qualify.** Pre-check on salient entity + capability to disable.
- [ ] **Latency under load.** Follow-up frame if inline misses budget?
- [x] **v1 scope:** inline-only; proactive push (Phase 59) deferred until inline feedback
  validates the engine.
