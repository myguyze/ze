# Salience & Relevance Model — Spec

> **Package:** `ze-memory`, `ze-correlation` (consumer)
> **Phase:** 56
> **Status:** Pending
> **Depends on:** Signal Substrate ([55-signal-substrate.md](55-signal-substrate.md)), News Preferences ([50-news-preferences.md](50-news-preferences.md)), User Profile ([14-user-profile.md](14-user-profile.md)), Core Memory ([../core/06-memory.md](../core/06-memory.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| Relevance set projection | 🔲 Pending |
| Signal admission gate | 🔲 Pending |
| Surfacing bar | 🔲 Pending |
| Feedback-driven threshold tuning | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

Salience is the single highest-risk part of proactive correlation. Without it the graph
floods with noise and Ze becomes a spam/conspiracy generator. This phase defines, in one
place:

1. **Where signals come from** and how an item earns a place in the graph (admission).
2. **What "the user cares about"** means, computed from memory — the *relevance set*.
3. **The bar** an item or a hypothesis must clear before it costs the user attention.

The design principle: salience is **grounded in the user, not in the world**. An item is
salient because it touches what the user has shown they care about (profile, preferences,
goals, conversations, engagement) — or because its intrinsic magnitude is high enough that
ignoring it would be negligent. This is the bounded-relevance principle from the
Correlation Engine ADR, made concrete and computable.

---

## Responsibilities

- Project memory into a **relevance set**: weighted entities and topics the user cares
  about, derived from durable and recent signals.
- Define the **admission gate** that decides whether a raw `Signal` enters the graph
  (Phase 55 calls this before `ingest_signal`).
- Define the **surfacing bar** that decides whether a formed hypothesis (Phase 57) is
  allowed to reach the user — inline (Phase 58) or push (Phase 59, deferred).
- Keep both gates cheap and explainable: every score must decompose into named
  contributions Ze can cite ("relevant because: active goal X, profile interest Y").
- Provide a feedback path so user reactions tune thresholds over time.

---

## Out of Scope

- Anchoring signals into the graph (Phase 55).
- Forming or wording hypotheses (Phase 57).
- A general engagement-telemetry/click-tracking system. Engagement here means coarse,
  already-available signals (follow-up questions, explicit reactions), not pixel tracking.
- Per-user model training or learned rankers. Thresholds are tuned by simple bounded
  feedback, not ML.

---

## The Relevance Set

The relevance set is the user's interest fingerprint: a weighted map of entities and
topics, projected from memory on demand (cached, short TTL).

```python
# core/ze-memory/ze_memory/types.py

@dataclass
class RelevanceEntry:
    key: str                      # entity id or normalized topic
    kind: Literal["entity", "topic"]
    weight: float                 # 0..1
    sources: list[str]            # why: ["profile:topics", "goal:...", "episode:recent"]

@dataclass
class RelevanceSet:
    entries: dict[str, RelevanceEntry]
    built_at: datetime
```

### Sources and base weights

| Source | Signal | Base weight | Decay |
| ------ | ------ | ----------- | ----- |
| Profile facets (`topics`, `preferences`) | durable, synthesized | High | none (stable) |
| Explicit preferences (`news_interest`, `topic_interest`) | user stated | High | none |
| Active goals (titles + linked entities) | current projects | Medium | ends with goal |
| Recent episode entities | conversation in last N days | Medium | time decay |
| Engagement (follow-ups, reactions to prior pushes) | demonstrated interest | Medium→High | slow decay |
| Graph centrality | entity already richly connected in user's graph | Low | none |

Negative preferences (`news_exclusion`, "stop showing X") subtract or zero a key — reusing
the Phase 50 exclusion taxonomy so news and correlation share one notion of "don't care".

```python
# core/ze-memory/ze_memory/relevance.py
class RelevanceModel:
    def __init__(self, memory_store, goal_provider) -> None: ...
    async def build(self) -> RelevanceSet: ...
    def score(self, rset: RelevanceSet, entities: list[str], topics: list[str]) -> RelevanceScore: ...
```

```python
@dataclass
class RelevanceScore:
    value: float                  # 0..1
    contributions: list[str]      # explainable: matched keys and their weights
```

---

## Gate 1 — Signal Admission (cheap, mostly non-LLM)

Called by Phase 55 before `ingest_signal`. Keeps the graph bounded.

```
admission = w_rel * relevance_to_user + w_mag * intrinsic_magnitude
admit if admission >= τ_admit
```

- `relevance_to_user`: `RelevanceModel.score(signal.entities, signal.topics)`.
- `intrinsic_magnitude`: `signal.magnitude` (source-supplied, per-source normalized so one
  noisy source cannot dominate).
- The LLM is **not** in this path. Admission is vector/lookup math so it can run on every
  fetched item cheaply.

Rationale for the user's question "how does the LLM know what to surface": at ingestion it
mostly does **not** — a cheap relevance computation does. The LLM is reserved for Gate 2 /
correlation, where it is expensive and worth it.

### Admission outcomes

| admission | Outcome |
| --------- | ------- |
| `>= τ_admit` | Ingest as event (Phase 55) |
| `τ_watch <= admission < τ_admit` | Hold in a lightweight watch buffer (no graph write); admit if a later related signal raises combined relevance |
| `< τ_watch` | Drop |

The watch buffer is what lets a *pair* of individually-marginal items become jointly
salient — the mechanism behind "two small events that only matter together".

---

## Gate 2 — Hypothesis Surfacing

The surfacing bar depends on the **delivery surface**, because the cost of being wrong
differs by orders of magnitude. An unprompted push interrupts the user; an inline section
merely enriches an answer they already asked for. There are therefore two bars, and
`τ_inline < τ_push`.

### Inline bar (Phase 58 — low)

Applied when correlation runs during a turn the user initiated. Relevance is implicit (the
user asked about the topic) and there is no interruption, so the bar is minimal:

| Condition | Threshold |
| --------- | --------- |
| Recall guarantee | ≥2 distinct `graph_recall` items (Phase 57) |
| Correlation confidence | `>= τ_inline` (low) |

No novelty or budget gate — re-asking may legitimately re-surface the same connection.

### Push bar (Phase 59 — high, the interrupt bar; deferred post-v1)

Applied by the proactive consumer after a hypothesis is formed. A hypothesis is pushed only
if **all** hold:

| Condition | Threshold | Source |
| --------- | --------- | ------ |
| Recall guarantee | ≥2 distinct `graph_recall` items | Phase 57 |
| Correlation confidence | `>= τ_push` | LLM self-rating, calibrated by feedback |
| Evidence count | `>= 2` grounded items | each with a stable id (`external_ref`/episode id) |
| Relevance to user | `>= τ_rel` | `RelevanceModel.score` over involved entities |
| Novelty | not embedding-similar to a recent push | `PushLogStore` + embedding |
| Push budget | within rate limit | `PushLogStore` window |

If any fails, the hypothesis is stored (for the weekly digest / on-demand recall) but not
pushed. "Worth storing" and "worth interrupting you" are deliberately different bars.

---

## Feedback Loop

Pushes carry lightweight actions (reuse confirmation/action frames): **useful** /
**not relevant** / **mute topic**.

- `useful` on a hypothesis nudges `τ_push`/`τ_rel` (and `τ_inline`) down slightly (more like this).
- `not relevant` nudges them up; repeated on a topic lowers that topic's relevance weight.
- `mute topic` writes a `news_exclusion`-style negative preference (shared taxonomy).

Tuning is bounded (clamped to `[τ_min, τ_max]`) and global in v1, not per-topic learned
models. The point is drift correction, not a recommender.

---

## Configuration

```yaml
# config/config.yaml
correlation:
  salience:
    admission:
      tau_admit: 0.55
      tau_watch: 0.35
      w_relevance: 0.7
      w_magnitude: 0.3
      watch_buffer_ttl_hours: 48
    surfacing:
      tau_push: 0.6            # interrupt bar (proactive push, Phase 59 — deferred)
      tau_inline: 0.45         # low bar (inline section, Phase 58 — v1); must be < tau_push
      tau_relevance: 0.5
      min_evidence: 2
      novelty_similarity_max: 0.85
    budget:
      max_pushes_per_day: 3
    feedback:
      step: 0.05
      tau_min: 0.4
      tau_max: 0.85
    relevance:
      episode_lookback_days: 30
      cache_ttl_minutes: 30
```

---

## Dependencies

| Dependency | Purpose |
| ---------- | ------- |
| `ze_memory` profile / facts / graph | relevance projection |
| Phase 50 preference taxonomy | shared include/exclude semantics |
| `ze_proactive.PushLogStore` | novelty + budget |
| embeddings singleton | novelty similarity |

---

## Test Plan

- Relevance set includes profile topics, explicit preferences, active goals, recent
  episode entities; excludes muted topics.
- Admission admits a signal about an active-goal entity; drops an unrelated low-magnitude
  signal; holds a marginal one in the watch buffer.
- Watch buffer: two marginal related signals jointly cross `τ_admit`.
- Surfacing bar rejects single-evidence hypotheses and low-confidence hypotheses.
- Novelty: a near-duplicate of a recent push is suppressed.
- Budget: pushes beyond `max_pushes_per_day` are stored not pushed.
- Feedback: `not relevant` raises thresholds within clamps; `mute topic` creates an
  exclusion that admission honors next run.
- Every score exposes `contributions` for explainability ("relevant because…").

---

## Open Questions

- [ ] Initial calibration: with no feedback history, what are sane default thresholds so
  Ze is neither silent nor spammy in week one? (Conservative defaults + a dev "dry-run"
  mode that logs would-be pushes without sending?)
- [ ] Should the relevance set be a materialized table (refreshed by consolidation) or
  computed on demand with a cache? (Leaning on-demand + cache for v1.)
- [ ] Is global threshold tuning enough, or do we need per-topic thresholds to stop one
  noisy domain from desensitizing all correlation?
- [ ] How does intrinsic magnitude get normalized across heterogeneous sources fairly
  (news vs finance vs legal)?
- [ ] Should engagement weighting risk a feedback loop where Ze over-focuses on whatever
  the user last reacted to (the "banana" failure from Phase 50, one level up)?
