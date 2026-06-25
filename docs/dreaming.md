# Ze — Dreaming

Ze runs an offline **dream phase** when it is not in active use. The phase replays
recent experience, compresses it, tests abstractions, and promotes only validated
changes into stable memory. The point is not random generation — it is a controlled
learning loop that improves retention, abstraction, and robustness.

**Package:** `core/ze-memory/ze_memory/dream/`
**Architecture:** [specs/arch/dream-memory.md](../specs/arch/dream-memory.md)
**Implementation spec:** [specs/phases/78-dream-memory.md](../specs/phases/78-dream-memory.md)

---

## Overview

```mermaid
flowchart TB
  subgraph Wake["Wake Phase"]
    U["User interaction"]
    T["Tool use / outcomes"]
    E["Episodic capture"]
    S["Salience scoring"]
    U --> E
    T --> E
    E --> S
  end

  subgraph ShortTerm["Short-Term Memory"]
    STM["Episodic buffer\nrecent traces + provenance"]
  end

  subgraph Sleep["Sleep Phase"]
    R["NREM replay\nrehearse important episodes"]
    P["Compression\nmerge, dedupe, summarize"]
    D["REM dreaming\nsynthesis + stress-tests"]
    C["Critic\nNLI gates + adversarial review"]
  end

  subgraph LongTerm["Long-Term Memory"]
    LM["Semantic memory\nstable facts and abstractions"]
    PM["Policy / skill memory\nheuristics and strategies"]
    FM["Forgetting / decay\nlow-value or stale traces"]
  end

  subgraph Morning["Morning Integration"]
    J["Dream journal\nwhat changed and why"]
    V["Validation\naccept / reject / revise"]
  end

  S --> STM
  STM --> R
  R --> P
  P --> LM
  P --> PM
  P --> D
  D --> C
  C --> V
  V --> LM
  V --> PM
  V --> FM
  C --> J
  J --> U
```

![Ze Dream Memory Cycle](assets/dream-memory-cycle.svg)

---

## How it works

1. **Wake** — Ze captures experiences with provenance. Every new episode is tagged
   asynchronously with `replay_score`, `source` (`ze_observed` or `user_asserted`), and
   a sensitive-entity flag. Tagging does not block the conversation write path.

2. **Sleep (NREM)** — The nightly job replays high-priority episodes, compresses old
   sessions, deduplicates facts, decays stale traces, and detects schema and policy
   clusters. No LLM calls in this phase.

3. **Dream (REM)** — For each cluster candidate, a generator synthesises insights,
   procedures, hindsight facts, or plan stress-tests. All outputs land in a staging
   buffer (`memory_dream_artifacts`) with `status=pending`.

4. **Critic** — Each staged artifact passes three cheap pre-gates (NLI groundedness,
   embedding novelty, retrievability) and two adversarial LLM critic calls. Both critics
   must pass.

5. **Morning integration** — Well-supported artifacts auto-promote to `memory_facts` or
   `memory_procedures` with full lineage. Borderline cases go to a review queue. Rejected
   artifacts trigger forgetting on their source episodes. A dream journal entry surfaces
   what changed.

Nothing synthetic writes directly to live memory. Every promoted fact carries
`provenance=synthesized`, `dream_run_id`, and `derived_from` lineage for rollback.

---

## What this achieves

- Better memory retention through targeted replay and decay.
- Better abstraction via schema and policy cluster synthesis.
- Better self-correction via hindsight relabeling and plan stress-tests.
- Lower risk of stale or duplicated memory through dedup and novelty gates.
- A visible dream journal that explains what changed and why.

---

## Phase split

| Sub-phase | Status | What ships |
|-----------|--------|------------|
| **78a** | Done | Sleep pass, wake hook, migration, dream journal API, retrieval weight enforcement |
| **78b** | Pending | Dream synthesis, NLI gates, two-critic pipeline, auto-promotion, review UI |

78a delivers useful consolidation before any LLM synthesis risk. 78b adds the full
dream→critic→promote loop once episode selection is validated in production.

**NLI model (Phase 79, done):** `cross-encoder/nli-deberta-v3-small` loads as a shared
singleton in `ze_memory/nli.py` — used for write-time contradiction, nightly dedup,
session-cached retrieval re-rank, and correlation grounding. Phase 78b's `Gate1_NLI`
in `gates.py` will import from the same module (no second download).

### 78a — user-visible

- Nightly sleep pass cleans episodes, compresses sessions, deduplicates facts, identifies
  schema and policy clusters (no synthesis yet).
- Morning briefing: "Ze processed N episodes overnight, found M schema clusters."
- Dream runs visible at `GET /api/v0/memory/dream/journal`.
- Episode retrieval respects `retrieval_weight` (stale episodes rank lower).

### 78b — adds

- LLM synthesis: insights, procedures, hindsight facts, stress-tests.
- Full scoring pipeline: NLI + novelty + retrievability + two-critic.
- Auto-promotion with lineage and per-run rollback.
- `needs_review` notifications (once the React review page ships).
- Synthetic fact confidence decay and corroboration detection.

---

## Key tables

| Table | Purpose |
|-------|---------|
| `memory_episode_metadata` | Mutable dream fields for episodes (replay score, retrieval weight, source, sensitive flag) |
| `memory_dream_runs` | One row per nightly job execution |
| `memory_dream_artifacts` | Staging buffer for all synthetic outputs pre-promotion |
| `memory_dream_journal` | Per-run summary for morning briefing and user review |
| `memory_retrieval_cache` | Session-scoped NLI rerank order for facts/summaries (Phase 79; expired nightly by `DreamJob`) |

Source episode content in `memory_episodes` stays immutable. All dream-phase mutable
fields live on the metadata side table.

---

## Artifact types

| Type | Auto-promote? | Destination |
|------|---------------|-------------|
| `schema_candidate` | No (input to synthesis) | Staging only |
| `policy_candidate` | No (input to synthesis) | Staging only |
| `synthesized_insight` | Yes, if gates + support pass | `memory_facts` |
| `synthesized_procedure` | Yes, if gates + support pass | `memory_procedures` |
| `hindsight_fact` | Never — always `needs_review` | User decision |
| `plan_stress_test` | Yes, if gates + support pass | `memory_procedures` (risk heuristic) |

Counterfactual and perturbation artifact types are reserved in the enum but not invoked
until 78c.

---

## Configuration

```yaml
# config/config.yaml
dream:
  enabled: true
  cron: "0 3 * * *"           # default 3 AM
  max_replay_episodes: 100
  max_synthesis_per_run: 20
  max_total_llm_calls_per_run: 60
  auto_promote_min_support: 3
  auto_promote_min_distinct_sessions: 2
  auto_promote_min_temporal_spread_days: 7
  nli_groundedness_threshold: 0.75
  novelty_similarity_threshold: 0.92
  decay_cycles: 5
  decay_rate: 0.1
  synthesis_model: "anthropic/claude-haiku-4-5"
  critic_model: "anthropic/claude-sonnet-4-5"
```

Environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DREAM_REVIEW_NOTIFICATIONS_ENABLED` | `false` | Push notifications for `needs_review` artifacts |

See [configuration.md](configuration.md) for the full key list once wired.

---

## REST API

```
GET  /api/v0/memory/dream/journal
GET  /api/v0/memory/dream/artifacts              # status=needs_review
GET  /api/v0/memory/dream/artifacts/{id}
POST /api/v0/memory/dream/artifacts/{id}/approve
POST /api/v0/memory/dream/artifacts/{id}/reject
POST /api/v0/memory/dream/artifacts/{id}/revise
POST /api/v0/memory/dream/runs/{run_id}/rollback
```

The React review page at `/memory/dream` (78b) lists `needs_review` artifacts with
source episode excerpts and approve/reject/revise actions.

---

## Safety model

- **Staging buffer** — no synthetic output touches live memory until all gates pass.
- **Provenance** — `provenance=synthesized` facts are hedged in retrieval context
  ("Ze inferred this from a pattern").
- **Source tagging** — `user_asserted` episodes score lower and cap at 1 toward
  `support_count`.
- **Sensitive exclusion** — episodes linked to sensitive entities skip all dream passes.
- **Session contamination** — summaries that included synthetic facts are flagged
  `dream_influenced` and excluded from dream source selection until corroborated or
  rolled back.
- **Rollback** — `POST /runs/{run_id}/rollback` bulk-contradicts all facts from a run
  and flags contaminated session summaries for re-summarisation.

---

## Research basis

Dreaming in Ze draws on both neuroscience and ML literature:

- Experience replay and generative replay for continual learning.
- Wake/sleep consolidated learning architectures.
- Constitutional AI-style critic filtering of synthetic outputs.
- Sleep consolidation research on replay ordering and context reinstatement.

Full bibliography and architectural rationale:
[specs/arch/dream-memory.md](../specs/arch/dream-memory.md#research-foundation).

---

## Related docs

| Doc | What it covers |
|-----|----------------|
| [memory.md](memory.md) | Base memory layers — facts, episodes, retrieval |
| [scheduled-jobs.md](scheduled-jobs.md) | Proactive job scheduler and nightly job pipeline |
| [specs/phases/79-nli-model.md](../specs/phases/79-nli-model.md) | NLI cross-encoder — shared singleton, contradiction, retrieval cache |
