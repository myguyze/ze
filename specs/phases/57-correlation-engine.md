# Correlation Engine — Spec

> **Package:** `ze-correlation` (new core package)
> **Phase:** 57
> **Status:** Pending
> **Depends on:** Signal Substrate ([55-signal-substrate.md](55-signal-substrate.md)), Salience Model ([56-salience-relevance-model.md](56-salience-relevance-model.md)), Correlation Engine ADR ([../arch/correlation-engine.md](../arch/correlation-engine.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| `Hypothesis` type + store | ✅ Done |
| Neighbourhood retrieval | ✅ Done |
| LLM correlation step | ✅ Done |
| Provenance + recall guarantee | ✅ Done |
| `correlate()` entrypoint | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

This is the **engine** that runs the five-step loop: given seed entities/events, retrieve
their graph neighbourhood, ask an LLM whether there is a non-obvious connection, and return
a grounded, provenance-tagged hypothesis with explicit uncertainty. Today Ze can only
elaborate a connection once a human recalls the prior event and hands it over; this engine
performs the recall and the connection-spotting itself.

The engine is **surface-agnostic** — it forms hypotheses, it does not decide how they reach
the user. Delivery is specified in consumer phases:

- **Inline / reactive (Phase 58)** — v1 scope; enriches answers the user asked for.
- **Proactive / push (Phase 59)** — deferred post-v1; unprompted interrupts.

This phase specifies **only the engine core**. No graph wiring, no push job, no web UI.

---

## Responsibilities

- Accept seeds (entity/event ids) and a `mode` that bounds cost (`inline` = tighter hops/
  neighbourhood + latency budget; `proactive` = wider bounds for the future push consumer).
- Expand the graph neighbourhood around each seed (prior events, facts, episodes, goals,
  signals) and materialize the rows needed to build a prompt context.
- Run a single, tightly-scoped, **graph-only** LLM correlation step over the bounded
  neighbourhood.
- Require grounded evidence (ids) and a confidence rating from the model.
- Tag every piece of evidence with its **provenance** (`graph_recall` vs `live_search` vs
  `prompt_supplied`) and enforce the recall guarantee.
- Persist all formed hypotheses for on-demand recall, inline rendering, and (later) push.
- **Pin cited signals:** bump `expires_at` on every `memory_signals` row cited as evidence
  so the source record is never pruned while a live hypothesis references it.

---

## Out of Scope

- Anchoring signals (Phase 55) and computing salience/relevance (Phase 56).
- **Inline conversational surface (Phase 58)** — graph node, response section, web UI.
- **Proactive push consumer (Phase 59)** — job, scheduling, interrupt bar, feedback on
  pushes. Explicitly deferred post-v1.
- The plugin `SignalSource` contract (Phase 60).
- Multi-signal convergence (Phase 61).
- Live search corroboration in v1 — recall-only; see Open Questions.

---

## Module Location

```
core/ze-correlation/ze_correlation/
    __init__.py
    types.py            # Hypothesis, EvidenceRef
    engine.py           # CorrelationEngine
    store.py            # PostgresHypothesisStore
    prompts.py          # correlation prompt
```

`ze-correlation` depends on `ze-agents` (LLMClient protocol) and `ze-memory` (graph +
relevance). It must not depend on any plugin or on `ze-proactive` — delivery consumers
wire those in.

---

## Data Structures

```python
# core/ze-correlation/ze_correlation/types.py

@dataclass
class EvidenceRef:
    kind: Literal["event", "fact", "episode"]
    id: UUID
    label: str               # short human label, e.g. "Fable 5 ban (Jun 12)"
    external_ref: str | None # source url/id when the evidence is a signal-event
    origin: Literal["graph_recall", "live_search", "prompt_supplied"]
    retrieved_at: datetime   # when this piece entered the neighbourhood
    ingested_at: datetime | None = None  # when it first entered memory (graph_recall only)

@dataclass
class Hypothesis:
    id: UUID
    summary: str             # one-line connection, neutral and hedged
    narrative: str           # the reasoning, with uncertainty made explicit
    relation: Literal["pattern", "causal_guess", "tension", "convergence"]
    confidence: float        # LLM self-rating, 0..1
    relevance: float         # Phase 56 RelevanceScore.value
    evidence: list[EvidenceRef]
    entities: list[UUID]
    created_at: datetime
    surfaced: bool           # True when shown inline or pushed
    feedback: Literal["useful", "not_relevant", "muted"] | None = None
```

---

## Interface Contract

```python
# core/ze-correlation/ze_correlation/engine.py

class CorrelationEngine:
    def __init__(
        self,
        memory_store,            # graph expand + retrieval
        relevance_model,         # Phase 56
        llm_client,              # ze_agents LLMClient protocol
        hypothesis_store,
        settings,
    ) -> None: ...

    async def correlate(
        self,
        seeds: list[UUID],
        *,
        mode: Literal["inline", "proactive"],
    ) -> list[Hypothesis]:
        """Expand neighbourhood, run the graph-only correlation step, tag provenance,
        enforce the recall guarantee, persist. Returns formed hypotheses WITHOUT delivering
        them. `mode` only bounds cost (inline = tighter hop/neighbourhood + latency budget).
        Consumers (Phase 58/59) apply surface-specific bars and delivery."""
```

### Pipeline (per seed)

1. **Neighbourhood** — `graph.expand(seed_ids, max_hops=N, limit=K)` → events, facts,
   episodes; plus active goals. Bounds depend on `mode`.
2. **Relevance prefilter** — drop neighbourhoods whose combined relevance `< τ_rel`
   before spending an LLM call (proactive mode only; inline skips — user asked).
3. **Correlation call** — one LLM call over the neighbourhood, **graph-only: no web/search
   tool is available in this step**. The prompt demands: connection summary, reasoning with
   explicit uncertainty, `relation` type, a confidence in `[0,1]`, and **evidence ids drawn
   only from the provided neighbourhood** (no outside facts). Reject/no-op if the model
   cites ids not in the input. Every cited item is tagged `origin="graph_recall"`.
4. **Recall guarantee** — a hypothesis is *formed* only if at least two `graph_recall`
   evidence items connect *distinct* prior signals/events. Consumers apply additional bars
   before surfacing (Phase 56).

---

## Correlation Prompt (shape)

```text
You are given a focal event and its neighbourhood (prior events, facts, past
conversations) for ONE user. Decide whether there is a non-obvious connection.

Rules:
- Use ONLY the provided items. Cite each claim by its [id].
- If there is no real connection, say so. Do not invent one.
- Express uncertainty plainly. You are offering a hypothesis, not a verdict.
- Prefer disconfirming evidence when present.

Output JSON: { summary, narrative, relation, confidence, evidence_ids[] }
```

---

## Evidence Provenance & the Recall Guarantee

The motivating session (confirmed from `memory_episodes`) showed the failure mode this
section exists to prevent: Ze *searched* for both the event and the prior connection, and
the user supplied the link. From the outside that can look identical to genuine
correlation. The engine must be able to prove which one happened.

Every `EvidenceRef` therefore carries an `origin`:

| `origin` | Meaning | Counts toward recall? |
| -------- | ------- | --------------------- |
| `graph_recall` | retrieved from the memory graph during neighbourhood expansion | **Yes** |
| `live_search` | fetched by a corroboration search *after* a connection was found | No |
| `prompt_supplied` | handed in by the user / an upstream caller | No |

**Why it matters:**

- **Honest framing.** A hypothesis built only from `live_search` evidence is not
  correlation — it is search. Graph-recalled evidence licenses "I connected this to
  something from {ingested_at}"; search-only does not.
- **Anti-degradation.** Without this, the engine can silently regress into a search
  wrapper. The recall guarantee (≥2 distinct `graph_recall` items) is the structural
  defence.
- **Auditability.** Provenance must be assigned by the engine from *where the item
  actually came from* (graph store vs search call), never inferred from model narration.

This also feeds Phase 61: convergence is only meaningful over graph-recalled history.

---

## Database Schema

```sql
CREATE TABLE correlation_hypothesis (
    id           UUID PRIMARY KEY,
    summary      TEXT NOT NULL,
    narrative    TEXT NOT NULL,
    relation     TEXT NOT NULL,
    confidence   REAL NOT NULL,
    relevance    REAL NOT NULL,
    evidence     JSONB NOT NULL,
    entities     JSONB NOT NULL,
    surfaced     BOOLEAN NOT NULL DEFAULT false,
    feedback     TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX correlation_hypothesis_created_idx ON correlation_hypothesis (created_at DESC);
```

The `evidence` JSONB holds each `EvidenceRef` including its `origin`, `retrieved_at`, and
`ingested_at`.

---

## Configuration

```yaml
# config/config.yaml
correlation:
  engine:
    enabled: true
    max_hops_inline: 1
    max_hops_proactive: 2
    neighbourhood_limit_inline: 15
    neighbourhood_limit_proactive: 30
    max_seeds_inline: 5          # top-N seeds by relevance when turn yields more
    timeout_seconds_inline: 5    # hard timeout; drop silently if exceeded
    model: "anthropic/claude-haiku-4-5"
```

Scheduling, push thresholds, and `dry_run` live in Phase 59.

---

## Dependencies

| Dependency | Purpose |
| ---------- | ------- |
| `ze_memory` graph + relevance | neighbourhood + relevance |
| `ze_agents.LLMClient` | correlation call |
| `ze_core.telemetry` cost context | per-run cost tracking |

---

## Test Plan

- Neighbourhood expansion reaches a **previously ingested** prior event from a new
  signal-event sharing an entity. The prior event must be seeded in the graph, *not* in the
  prompt; the test fails if the engine only "works" when spoon-fed.
- LLM step rejected when it cites an id not in the neighbourhood (anti-hallucination).
- The correlation call has no web/search tool available.
- All evidence cited in the correlation step is tagged `origin="graph_recall"`.
- **Recall guarantee:** a hypothesis whose connection rests on fewer than two distinct
  `graph_recall` items is not formed.
- "No connection" output produces no hypothesis.
- `correlate(mode="inline")` honours tighter hop/neighbourhood bounds than
  `mode="proactive"`.
- A golden replay of the Fable 5 / Pentagon scenario: the Pentagon event is seeded into the
  graph in advance; only the Fable 5 signal is fed at run time. The engine must recall the
  Pentagon event and yield a `tension`/`causal_guess` hypothesis citing both.

---

## Open Questions

- [x] **Cost bounding:** cap per-seed neighbourhood using `BoundedExpansionPolicy`
  (already exists). Inline uses tight bounds (max_hops=1, limit=15); proactive uses wider
  bounds (max_hops=2, limit=30) — both already in config. If the seed set exceeds 5
  entities, take the top-N by relevance score before expanding. No batching or clustering
  in v1 — inline seed sets are naturally small (one turn's entities).
- [x] **Hypotheses written back to graph:** No in v1. The `correlation_hypothesis` table
  is the persistence layer. Writing derived nodes back into the graph risks feedback loops
  and pollutes the recall guarantee (graph-recalled evidence must be *observed*, not
  derived). Revisit post-v1 if building on prior hypotheses proves valuable.
- [x] **Confidence calibration:** LLM self-rated confidence is used as-is in v1. The
  inline bar is deliberately low (τ_inline=0.45 from Phase 56) so the engine shows
  connections frequently; inline feedback (useful/not_relevant) provides calibration signal
  before Phase 59 push is enabled. Sufficient for v1.
- [x] **Evidence provenance:** required; graph-only correlation step; recall guarantee
  gates hypothesis formation. (Confirmed from motivating session logs.)
- [x] **`live_search` in v1:** no — v1 is recall-only and unambiguous.
- [x] **≥2 distinct `graph_recall` threshold:** Keep strict in v1. A single recalled item
  is indistinguishable from `prompt_supplied` from the user's perspective; two distinct
  items are the minimum for "I noticed a connection". Relax only with empirical evidence
  from inline feedback data.

---

## Implementation Notes (resolved before coding)

**Package placement:** `ze-correlation` is a new core package (not a plugin). The engine
is infrastructure — it does not know about any domain. Plugins contribute signals via
Phase 60. Adding it as a plugin would invert the dependency.

**Migration:** The `correlation_hypothesis` table migration lives in
`apps/ze-api/migrations/` (same pattern as `memory_signals`), not inside the package.

**Neighbourhood materialization:** After `GraphStore.expand()` returns bucketed IDs, the
engine fetches actual rows from the appropriate tables via `memory_store` methods:
- Facts: `PostgresMemoryStore.list_recent_facts()` filtered by ID (add `get_facts_by_ids`)
- Episodes: similar
- Signals: query `memory_signals` by the `signal_ids` from `GraphExpansion`
The goal is to build a rich prompt context; each item is rendered as a short text block
with its ID, type, and timestamp so the LLM can cite it.

**Signal pinning:** When a hypothesis is formed, bump `expires_at` on every cited
`memory_signals` row so the evidence is never pruned while a live hypothesis references it.
Add a `pin_signals(signal_ids, until)` helper to `PostgresMemoryStore`.

**Inline latency budget:** Add `timeout_seconds_inline: 5` to the config. If the
correlation call exceeds this, drop silently — Phase 58 must not block the main response.

**Seed source (for Phase 58):** Seeds are entity UUIDs extracted from the user's current
turn context — specifically the `linked_entity_ids` available in `AgentState` after
`fetch_context`. Phase 58 passes these to `correlate()`. If no entities are in context,
skip correlation.

**`InsightEngine` separation:** InsightEngine stays separate. It is intra-personal
(synthesises facts about the user) and runs as a weekly job. The correlation engine is
cross-domain (connects external events to user history) and runs inline. They answer
different questions with different lifecycles; no absorption.
