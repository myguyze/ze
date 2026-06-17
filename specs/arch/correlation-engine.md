# Correlation Engine — Architecture Decision

> **Status:** Proposed
> **Scope:** `ze-memory`, `ze-correlation` (new), `ze-proactive`, all signal-emitting plugins
> **Phases:** 55 (substrate), 56 (salience), 57 (engine), 58 (inline — v1), 59 (push — deferred), 60 (plugin contract), 61 (convergence — deferred)

---

## Context

The motivating session is instructive precisely because of what Ze did **not** do. The
user asked why a model release was treated harshly by a government. Ze answered the
current event. Then **the user**, not Ze, surfaced the connection to a prior, separate
event (the same company refusing a defence deal months earlier); Ze, once pointed at it,
filled in supporting detail (likely via web search) and articulated the pattern with
explicit uncertainty.

So the human supplied the two things that matter most: the **recall** of the relevant
prior event, and the **hunch that the two were connected**. Ze only did the easy part —
elaborating a connection it was handed. That is the gap this work closes.

The goal is to let Ze run the **whole** loop: hold the prior event itself (assuming it was
ingested earlier as a signal), recall it when the user asks about a related topic (inline,
Phase 58 — v1), and eventually surface connections unprompted (proactive push, Phase 59 —
deferred).

The full loop decomposes into five steps. Today Ze only does steps 3–5, and only when a
human has already done steps 1–2 for it:

1. A **salient event arrives and is retained** — not just seen and forgotten.
2. Ze **recalls a related prior event / fact / conversation on its own** ← the missing
   capability; in the motivating session the human did this.
3. Ze notices a **structural or causal pattern**.
4. Ze **cross-references** a confirming or disconfirming fact.
5. Ze produces a **hypothesis with explicit uncertainty**, leaving judgment to the user.

This ADR records how steps 1–2 (the actual gap) map onto Ze's existing primitives, and,
crucially, what the system deliberately is *not*.

A note that became a hard requirement: step 2 must be **recall**, not search. In the
motivating session Ze produced its detail by web-searching, and from the outside that is
indistinguishable from genuine recall. The engine must therefore tag every piece of
evidence with provenance (`graph_recall` vs `live_search` vs `prompt_supplied`), assign it
from where the item actually came from (never from the model's narration), and refuse to
present a search-built connection as something it "noticed". See Phase 57's recall
guarantee.

---

## Decision

Build a **bounded, relevance-gated correlation engine**, not a world model.

The system models only the neighbourhood of entities and events the user already cares
about — their interests, profile, goals, conversations, and signals plugins choose to
surface — and looks for non-obvious connections *inside that neighbourhood*. It never
attempts to model the world at large.

Three structural pieces, each a phase:

1. **Signal substrate (Phase 55)** — any plugin can promote a salient item into the
   shared memory graph as an `Event` linked to resolved `Entity` nodes. This is the only
   new substrate; it makes `PostgresGraphStore.expand()` traverse across domains
   (a news event and a past conversation about the same company become one neighbourhood).

2. **Salience & relevance model (Phase 56)** — a computable relevance score derived from
   memory (profile facets, explicit preferences, active goals, recent episode entities,
   engagement). This is the **admission gate** for signals and the basis for the
   **surfacing bar**. See "The bar" below.

3. **Correlation engine (Phase 57)** — a surface-agnostic **service** (not a job): given
   seed entities/events, it expands the graph neighbourhood, hands the bounded
   neighbourhood to an LLM with one task ("is there a non-obvious connection, pattern, or
   tension? cite evidence IDs; rate confidence"), and returns grounded, provenance-tagged
   hypotheses. The engine does not decide *how* a hypothesis reaches the user — that is the
   job of its consumers (below).

4. **Cross-plugin contract (Phase 60)** — a `SignalSource` hook on `ZePlugin` so
   finance, legal, calendar, email, etc. feed the same engine with zero engine changes.

### Delivery surfaces (two consumers of the same engine)

The engine is consumed two ways, with very different risk profiles:

- **Inline / reactive (Phase 58 — v1 scope)** — during a normal turn, when the user asks
  about a topic, the engine runs over the turn's entities and the agent appends a dedicated
  "connections" section to its answer. The user asked; the cost of surfacing is near zero.
- **Proactive / push (Phase 59 — deferred post-v1)** — on a cadence, the engine runs over
  recently admitted signals and pushes qualifying hypotheses via `ProactiveNotifier`. This
  *interrupts* the user, so its bar is far higher.

**Decision: v1 ships inline-only (Phase 58).** Proactive push (Phase 59) is explicitly
deferred until inline feedback validates the engine. Inline sidesteps the hardest problem
(deciding unprompted when to interrupt) and earns trust before autonomous pushes are
enabled. See the roadmap below.

---

## Why not a world model

A world model is unbounded, ungroundable, and is exactly where hallucinated correlations
live. The bounded-relevance approach is the Asimov/psychohistory insight scaled down: we
do not predict the world deterministically; we surface *pressure points* within the
user's neighbourhood and leave agency intact (step 5). Every surfaced hypothesis must
cite evidence IDs — Ze shows the dots, it does not assert the conclusion.

This keeps three properties:

- **Bounded compute and storage** — the graph only grows along the user's relevance set.
- **Groundedness** — no evidence, no push.
- **Human agency** — the output is always a hypothesis with uncertainty, never a verdict.

---

## The bar (salience, summarised)

Two distinct stages, two distinct gates. Detailed in Phase 56; summarised here because it
is the central design risk.

### Stage 1 — Signal admission (cheap, mostly non-LLM)

Most raw items (headlines, ticks, emails) must never enter the graph. An item is admitted
as a `Signal` only if it clears an **admission score**:

```
admission = relevance_to_user + intrinsic_magnitude
```

- `relevance_to_user`: overlap between the item's entities/topics and the user's
  **relevance set** (profile facets, explicit preferences, active goals, entities from
  recent episodes, engagement-weighted entities).
- `intrinsic_magnitude`: domain-supplied importance (a market crash matters even if the
  user never mentioned the ticker), capped so it cannot flood the graph.

The LLM is *not* the primary gate here — a cheap relevance computation is, so the graph
stays bounded and cost stays low.

### Stage 2 — Hypothesis surfacing

Critically, the surfacing bar depends on the delivery surface, because the cost of being
wrong differs by orders of magnitude:

**Inline bar (low)** — the user already asked about the topic, so relevance is implicit and
there is no interruption cost; the connection is just an extra section in an answer they
wanted. Requirements: passes the recall guarantee (≥2 distinct `graph_recall` items) and
`correlation_confidence >= τ_inline` (low). No novelty/budget gating — if the user asks
again, showing the same connection again is fine.

**Push bar (high)** — an unprompted push *interrupts* the user, so it must clear **all** of:

- `correlation_confidence >= τ_push` (high) — LLM self-rated, calibrated against feedback.
- `evidence_count >= 2` grounded items, each with a stable ID.
- `relevance_to_user >= τ_rel` — the involved entities sit in/near the relevance set.
- **novel** — not embedding-similar to a recently pushed hypothesis (`PushLogStore`).
- **within push budget** — rate-limited per period.

`τ_inline < τ_push`. User feedback ("useful" / "noise") tunes both over time. The asymmetry
is the reason inline ships first: it needs only the recall guarantee and a low confidence
floor, not the whole calibrated interrupt machinery.

---

## Build order (roadmap)

Phase numbers now match build order:

| Phase | Spec | v1? |
| ----- | ---- | --- |
| 55 | Signal substrate | Yes |
| 56 | Salience & relevance (admission + inline bar first) | Yes |
| 57 | Correlation engine (service core) | Yes |
| 58 | Inline conversational surface | **Yes — sole v1 consumer** |
| 59 | Proactive correlation push | **No — deferred post-v1** |
| 60 | Cross-plugin `SignalSource` | After v1 validates |
| 61 | Convergence & pressure points | Design-only; deferred |

1. **55 → 56 → 57 → 58** is the v1 slice. Ship this before anything else.
2. **59 (push)** only after Phase 58 inline earns trust via feedback.
3. **60 (SignalSource)** generalises signal emission once the substrate works with news.
4. **61 (convergence)** remains design-only until 55–60 and inline are proven.

The key point: v1 is inline-only. The engine earns trust on user-initiated turns before it
is ever allowed to interrupt.

---

## Mapping to existing primitives

| Need | Existing primitive | Gap |
| ---- | ------------------ | --- |
| Surface to user (push) | `ProactiveJob` + `ProactiveNotifier` + `PushLogStore` (dedup/budget) | none — reuse |
| Surface to user (inline) | orchestration graph node + `AgentState` + response section + web rendering | new node + a "connections" component (Phase 58) |
| Neighbourhood retrieval | `PostgresGraphStore.expand()`, predicates, `Entity`/`Event`/`Fact`/`Episode` | `Signal` is a new first-class node type (Phase 55); not yet in the graph |
| Pattern synthesis | `InsightEngine` (LLM over facts/episodes) | intra-personal only; reads legacy tables |
| Relevance signals | profile facets, `NewsPreference` model (Phase 50), active goals | not unified into one relevance score |
| Plugin contribution | `memory_policies()`, `configurable_services()`, `register_proactive_jobs()` | no `SignalSource` hook |

---

## Consequences

- **Positive:** reuses the push pipeline, the graph, and the synthesis precedent; the
  plugin seam is exactly where "any plugin contributes a factor" belongs; bounded and
  grounded by construction.
- **Negative / risks:** entity resolution must generalise beyond people (orgs, tickers,
  topics); `InsightEngine`'s legacy-table drift must be resolved if it becomes the
  synthesis surface; calibrating the surfacing bar needs a feedback loop or Ze becomes a
  spam/conspiracy generator.
- **Deferred:** proactive push (Phase 59) and convergence (Phase 61) are explicitly
  post-v1; calibrating the push bar without inline feedback risks spam.

---

## Open Questions

- [x] **Signal node type:** `Signal` is a new first-class graph node (alongside
  `Event`/`Episode`/`Fact`), not a reuse of `Event`. Retrieval policies can explicitly
  include or exclude `Signal` nodes; `expand()` traversal stays clean. Provenance
  (`source` + `external_ref`) lets the engine reconstruct evidence from the source table.
- [x] **Topic entity type:** `Topic` is an entity type (alongside `person`, `org`,
  `ticker`, `place`, `product`). Coarse tags on the signal are insufficient for graph
  traversal — `Signal --MENTIONS--> Topic <--MENTIONS-- Episode` is the cross-domain
  link the engine needs.
- [x] **Signal retention:** Signals carry their own retention window (`retention_days`,
  default 90 days), independent of the source table's pruning schedule. The `Signal` node
  retains `title`, `summary`, and entity edges even after the source row is pruned. Phase
  57 is responsible for pinning cited signals (bumping `expires_at`) so evidence is never
  pruned while a live hypothesis references it.
- [x] **v1 scope:** inline-only (Phase 58). Proactive push (Phase 59) deferred until
  inline feedback validates the engine.
- [x] **Core package vs plugin:** `ze-correlation` is a core package. The engine is
  infrastructure — it has no domain knowledge. Plugins contribute signals via the Phase 60
  `SignalSource` hook; the engine just runs. Putting it in a plugin would invert the
  dependency (a plugin would own infrastructure that other plugins consume).
- [x] **Initial relevance calibration:** Phase 56 defaults work without feedback.
  Onboarding always collects profile facets; goals contribute if active. If the relevance
  set is empty (fresh user, no onboarding), admission falls back to magnitude-only, which
  is 0.0 for news in v1 — so nothing gets in. The engine degrades gracefully to a no-op
  rather than flooding with uncalibrated signals.
- [x] **Inline placement:** Graph node (not agent tool). A graph node runs unconditionally
  after `execute_tool` and before `write_memory`, so correlation always fires when the
  conditions are met — not only when the agent happens to call a tool. The node checks the
  relevance prefilter and drops silently if there is nothing to correlate. Phase 58 specifies
  the exact node and where it splices into the orchestration graph.
- [x] **Inline latency budget:** max_hops=1, neighbourhood_limit=15 for inline mode.
  The LLM correlation call is the expensive part; a hard 5-second timeout is applied
  (`timeout_seconds_inline: 5` in config). If the call exceeds this, the node drops
  silently — correlation must never block the main response.
- [x] **InsightEngine absorption:** InsightEngine stays separate. It is intra-personal
  (synthesises facts and episodes about the user themselves, weekly job) while the
  correlation engine is cross-domain (connects external events to user history, per-turn).
  They answer different questions with different lifecycles. No absorption.
