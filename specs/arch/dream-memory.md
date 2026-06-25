# Ze — Dream Memory Architecture

> **Package:** `ze-memory` (`dream/` submodule) + `ze-api` (job wiring)
> **Implementation spec:** [Phase 78 — Dream Memory](../phases/78-dream-memory.md)
> **NLI integration:** [Phase 79 — NLI Cross-Encoder](../phases/79-nli-model.md)
> **Status:** 78a implemented; 78b pending. Phase 79 (NLI singleton) done — see below.

---

## Context

Ze already has a mature memory stack: episodic capture, session summarisation, fact
deduplication, graph relationships, and proactive consolidation jobs. What it lacks is
an **offline learning loop** — a controlled phase where Ze replays recent experience,
compresses it, tests abstractions, and promotes only validated changes into stable
memory.

The biological metaphor is deliberate but not decorative. Sleep research distinguishes
NREM-like replay and consolidation from REM-like recombination and imagination. ML
literature on continual learning shows the same ordering matters: compress and deduplicate
first, then generate variants, then filter with a critic. Mixing these phases degrades
output quality.

The single-user model gives freedom to redesign memory boundaries for clarity. The goal
is not to bolt dreaming onto existing tables, but to add a staging buffer, provenance
lineage, and critic-gated promotion path that no published production memory system
(MemGPT, Mem0, A-MEM, TiMem) currently implements at this level.

---

## Goals

1. Improve memory retention, abstraction, and self-correction without letting synthetic
   outputs overwrite trusted memory.
2. Run useful offline consolidation (Sleep pass) before any LLM synthesis ships.
3. Gate every synthetic artifact through cheap pre-checks (NLI, embedding novelty,
   retrievability) and a two-call adversarial critic before promotion.
4. Provide full provenance lineage and per-run rollback for every promoted synthetic fact.
5. Surface a dream journal so the user can see what changed and why.

---

## Non-Goals

- Generating synthetic episodes from scratch (no pure hallucination path).
- Re-summarising already-summarised content (`provenance=compressed` is never source).
- Real-time dreaming during active sessions.
- Counterfactuals and perturbation checks in v1 (types reserved; deferred to 78c).
- Training or fine-tuning any model.

---

## Four-Phase Pipeline

```
Wake  →  Sleep (NREM)  →  Dream (REM)  →  Morning Integration
```

| Phase | Biological analogue | What happens | LLM calls |
|-------|---------------------|--------------|-----------|
| **Wake** | Experience capture | Tag episodes with `replay_score`, `source`, `has_sensitive_entity` at write time | None |
| **Sleep** | NREM replay + consolidation | Replay top episodes, compress sessions, dedup facts, decay stale traces, detect schema/policy clusters | None |
| **Dream** | REM recombination | Synthesise insights, procedures, hindsight facts, plan stress-tests into staging buffer | Haiku generator |
| **Morning** | Waking integration | Three gates + two-critic pipeline; auto-promote, review queue, or forget | Sonnet critic + NLI |

No phase writes synthetic outputs directly to live memory. All dream products live in
`memory_dream_artifacts` until gates pass, support thresholds are met, or the user
explicitly approves, revises, or rejects them.

---

## Phase Split (78a / 78b)

| Sub-phase | Ships | User-visible value |
|-----------|-------|-------------------|
| **78a** | Sleep pass + foundation (migration, types, wake hook, journal, job wiring) | Nightly cleanup, session compression, fact dedup, schema/policy cluster detection; dream journal API; retrieval respects `retrieval_weight` |
| **78b** | Dream pass + NLI gates + two-critic + promoter + REST review API + React page | LLM synthesis, auto-promotion with lineage, `needs_review` queue, synthetic fact decay, rollback |

78b must not start until episode selection and sensitive-entity tagging from 78a are
validated in production.

---

## Memory Layer Model

```
┌─────────────────────────────────────────────────────────────┐
│  Short-Term Memory (Episodic Buffer)                        │
│  memory_episodes (immutable source content)                 │
│  memory_episode_metadata (mutable dream fields — side table)│
└────────────┬────────────────────────────────────────────────┘
             │ Sleep: replay, compress, dedup, decay
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Dream Buffer (Staging)                                     │
│  memory_dream_artifacts — all synthetic outputs pre-promote │
└────────────┬────────────────────────────────────────────────┘
             │ Dream: synthesis → gates → critic
             ▼
┌─────────────────────────────────────────────────────────────┐
│  Long-Term Memory                                           │
│  memory_facts (provenance=raw | synthesized)                │
│  memory_procedures (creation_method=synthesized)              │
│  memory_session_summaries (dream_influenced tracking)       │
└─────────────────────────────────────────────────────────────┘
```

**Hard invariants:**

- `memory_episodes` source content stays immutable; dream-phase mutable fields live on
  `memory_episode_metadata`.
- `provenance=compressed` records are never source material for further synthesis.
- `provenance=synthesized` records never overwrite `provenance=raw` records.
- Episodes with `has_sensitive_entity=True` are excluded from all dream passes.
- Every `memory_dream_artifacts` row carries non-empty `source_episode_ids`.
- `hindsight_fact` artifacts are never auto-promoted — always `needs_review`.

---

## Locked Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Phase split | 78a = Sleep + foundation; 78b = Dream synthesis + gates | Ship useful consolidation before LLM cost and risk |
| Episode mutability | `memory_episode_metadata` side table | Keeps source episodes immutable and auditable |
| NLI model | `cross-encoder/nli-deberta-v3-small` (~90MB local) | `LocalNLIClient` in `ze_core/nli.py` (Phase 80). 78b `Gate1_NLI` injects `NLIClient` — one download, one warm-up |
| Critic model | `anthropic/claude-sonnet-4-5` | Haiku-class holistic judges achieve only ~65–70% agreement on factual tasks |
| Generator model | `anthropic/claude-haiku-4-5` | Cost-efficient synthesis; critic is the quality gate |
| Fact conflict resolution | `max(created_at)` deterministic rule | Never LLM judgment on conflicts |
| `_classify_source()` | `user_asserted` when no tool outcomes and no calendar/email origin; else `ze_observed` | Prevents provenance laundering |
| Stress-test schema | `{risk, warning_signal, recommended_caution}` only | Conditional framing; critic rejects unconditional action verbs |
| Review UX | `DREAM_REVIEW_NOTIFICATIONS_ENABLED=false` until React page ships | Avoid push notifications with no action surface |
| Counterfactuals / perturbations | Cut from v1 | Scoring integration undefined; expensive with no measurable output |

---

## Scoring and Promotion Model

Every promotable artifact passes through this pipeline in sequence. Failure at any step
marks the artifact `rejected`.

```
artifact + source_episodes
    → Gate 1: NLI groundedness (faithfulness ≥ 0.75)
    → Gate 2: embedding novelty (max cosine < 0.92 to existing raw facts)
    → Gate 3: embedding retrievability (≥1 source episode in top-3 retrieval)
    → Critic Call A: adversarial challenge (sonnet, temp=0.1)
    → Critic Call B: constructive verify (sonnet, temp=0.3)
    → Support validation (support_count ≥ 3, distinct_sessions ≥ 2,
                          temporal_spread ≥ 7d, user_asserted_count ≤ 1)
    → Auto-promote | needs_review | reject
```

**Why `support_count ≥ 3` alone is insufficient:** three correlated episodes from the
same session can satisfy the threshold without independent evidence. Session diversity
and temporal spread break self-confirming belief clusters.

**Why tagging at write time:** the dream phase cannot retroactively assess salience.
`replay_score`, `source`, and `has_sensitive_entity` must be set when the episode is
captured.

**Why never re-compress summaries:** iterative summarisation is the primary mechanism
of semantic drift in LLM memory systems (TiMem's documented worst failure mode). Each raw
episode may be compressed once.

---

## Research Foundation

This architecture was derived from four parallel research streams:

1. **Neuroscience** — NREM/REM ordering, targeted memory reactivation (TMR), SHY
   synaptic homeostasis, context reinstatement during sleep.
2. **ML analogues** — Prioritized Experience Replay, Constitutional AI, generative replay
   safety, Reflexion, HER, continual learning catastrophic forgetting.
3. **Ze codebase survey** — existing memory layers, `ProactiveScheduler`,
   `MemoryConsolidator`, `GoalSuggestionJob` read→synthesize→gate→push pattern.
4. **Production LLM memory systems** — MemGPT/MemOS, Mem0, A-MEM, TiMem, D-Mem, RAGAS,
   LLM-as-judge literature.

### Key references

- Experience replay: [Continual Learning with Deep Generative Replay](https://arxiv.org/abs/1705.08690)
- Compressed replay: [REMIND Your Neural Network to Prevent Catastrophic Forgetting](https://arxiv.org/abs/1910.02509)
- Wake/sleep offline learning: [Wake-Sleep Consolidated Learning](https://arxiv.org/abs/2401.08623)
- Dream-like recombination: [Learning cortical representations through perturbed and adversarial dreaming](https://arxiv.org/abs/2109.04261)
- Sleep consolidation: Björn Rasch et al., *Odor Cues During Slow-Wave Sleep Prompt Declarative Memory Consolidation*
- Dream-linked memory: Erin E. Wamsley et al., *Dreaming of a Learning Task Is Associated with Enhanced Sleep-Dependent Memory Consolidation*
- Context reinstatement: Eitan Schechtman et al., *Memory consolidation during sleep involves context reinstatement in humans*

---

## Integration with Existing Ze Memory

| Existing component | Role in dream pipeline |
|--------------------|------------------------|
| `PostgresMemoryStore.write_episode()` | Wake hook — fire-and-forget metadata tagging |
| `SessionSummariser` | Sleep pass — session compression (delegate) |
| `MemoryConsolidator.dedup_facts()` | Sleep pass — fact deduplication (delegate) |
| `ProactiveScheduler` + `DreamJob` | Nightly cron orchestration |
| `BriefingJob` | Morning pull from `PostgresDreamStore.get_latest_journal_entry()` |
| `memory_facts.provenance` | Distinguishes raw vs synthesized facts in retrieval |

Ze already has the right structural hooks: `creation_method="synthesized"`, `reviewed`
flag, `ProactiveScheduler`, and the `GoalSuggestionJob` pattern are all reusable.

---

## Risks and Mitigations

### Launch-blocking

| Risk | Mitigation |
|------|------------|
| Synthetic memory re-enters its own source pool | Enforce `WHERE provenance = 'raw'` on all source queries; integration test |
| No review UX when notifications fire | Gate `needs_review` push behind `DREAM_REVIEW_NOTIFICATIONS_ENABLED` until React page ships |
| No rollback for auto-promoted facts | `POST /runs/{run_id}/rollback` before first auto-promotion run |

### Operational

| Risk | Mitigation |
|------|------------|
| `replay_score` novelty O(N) on write path | Defer exact novelty to nightly score-refresh; use pgvector ANN (`<=> LIMIT 5`) |
| Promotion not atomic | Single DB transaction; startup reconciliation for ghost promotions |
| LLM call budget unbounded | `max_total_llm_calls_per_run` global cap (default 60) |
| Dream pass on stale data (no new episodes) | `min_new_episodes_to_run` gate — skip Dream pass, not Sleep pass |
| Early-user silence (no auto-promotions for weeks) | Make empty journal state explicit; consider lower threshold for early-user mode |

### Known elephants

1. **Feature produces no value until enough data** — `support_count ≥ 3` with session
   diversity means weeks of silence for sparse users. Journal must explain why.
2. **Counterfactuals undefined in v1** — cut from scope; types reserved for 78c.
3. **NLI model is English-first** — Phase 79's `_is_latin()` guard skips NLI for
   non-Latin pairs (cosine fallback). 78b Gate 1 may add haiku LLM groundedness for
   non-English before multilingual deployment.

---

## Observability

Each dream run writes to `memory_dream_runs` and `memory_dream_journal`. The journal
records episodes scored, replayed, deduped, candidates detected, insights promoted, and
items pending review. REST API exposes runs, artifacts, and user decision endpoints.

Monitor: run duration, gate FAIL rates by gate, critic FAIL rate, auto-promotion count,
and `source_fact_ids` concentration (same fact sourcing >5 promoted artifacts → review).

---

## Related Documentation

| Document | Purpose |
|----------|---------|
| [docs/dreaming.md](../../docs/dreaming.md) | Developer guide — concepts, config, API surface |
| [specs/phases/78-dream-memory.md](../phases/78-dream-memory.md) | Full implementation spec — schema, API, steps |
| [specs/phases/79-nli-model.md](../phases/79-nli-model.md) | NLI cross-encoder integration details |
| [docs/memory.md](../../docs/memory.md) | Base memory system (facts, episodes, retrieval) |
