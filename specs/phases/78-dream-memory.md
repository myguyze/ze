# Ze Dreaming — Offline Memory Consolidation — Spec

> **Package:** `ze-memory` (new `dream/` submodule) + `ze-api` (job wiring)
> **Phase:** 78a (Sleep pass + foundation) / 78b (Dream pass + synthesis)
> **Architecture:** [arch/dream-memory.md](../arch/dream-memory.md)
> **Developer guide:** [docs/dreaming.md](../../docs/dreaming.md)
> **Status:** Pending

**Architectural decisions locked:**
- Phase split: 78a = Sleep pass + foundation; 78b = Dream pass + NLI gates + two-critic pipeline
- Review UX: `needs_review` push notifications gated behind `DREAM_REVIEW_NOTIFICATIONS_ENABLED` feature flag until React review page ships
- NLI model: `cross-encoder/nli-deberta-v3-small` (~90MB) added as a second local model singleton in `gates.py` (ships in 78b)
- Episode mutability: decay fields (`retrieval_weight`, `replay_count`, `replay_score`, `last_replayed_at`, `provenance`, `source`, `has_sensitive_entity`) live on a separate `memory_episode_metadata` side table, not directly on `memory_episodes` — keeps the source record immutable
- Critic model: `anthropic/claude-sonnet-4-5` (confirmed available on OpenRouter, already in use in codebase)
- Conflict resolution: deterministic `max(created_at)` for fact conflicts — never LLM judgment
- `_classify_source()`: `user_asserted` when episode has no tool call outcomes and no calendar/email signal origin; `ze_observed` otherwise
- Stress-test promotion schema: locked to `{risk, warning_signal, recommended_caution}` — conditional framing only; critic rejects unconditional action verbs

---

## Research Basis

This spec was derived from four parallel research streams:
- Neuroscience: sleep memory consolidation (NREM/REM functions, TMR studies, SHY theory)
- ML analogues: PER, Constitutional AI, TiMem, Reflexion, HER, generative replay safety
- Ze codebase survey: existing memory layers, ProactiveScheduler, MemoryConsolidator
- Production LLM memory systems: MemGPT/MemOS, Mem0, A-MEM, TiMem, D-Mem, RAGAS, LLM-as-judge literature

Key resolved findings that drive the architecture:

1. **NREM-then-REM ordering is causal** — compress/deduplicate first, then recombine. Mixing phases degrades output quality.
2. **Importance must be tagged at write time** — the dream phase cannot retroactively assess salience. Episodes need a `replay_score` at creation.
3. **Never re-compress a summary** — model collapse risk. Each raw episode may be compressed once. This directly addresses TiMem's documented worst failure mode (facts degrading after two compression hops).
4. **Single holistic LLM critic is unreliable** — haiku-class models used as holistic judges achieve only ~65–70% agreement with human annotators on factual tasks (vs ~85% for sonnet-class). They have a systematic "too permissive" failure mode on plausible-but-unsupported claims. Replace with three cheap pre-gates (NLI groundedness, embedding novelty, embedding retrievability) followed by an LLM critic narrowed to contradiction detection only, using sonnet-class for the critic and haiku-class for the generator.
5. **`support_count >= 3` alone is not independent evidence** — three correlated episodes from the same session (all retrieved the same prior wrong fact as context) can satisfy the threshold without providing independent support. Require: supporters span >= 2 distinct `session_id`s AND >= 7 calendar days. This breaks self-confirming belief clusters — the worst-case failure mode.
6. **Provenance laundering is a concrete attack path** — a user-asserted episode ("user told me X") looks identical to a Ze-observed fact by the time the critic evaluates it. Tag episodes with `source=ze_observed | user_asserted` at write time. User-asserted episodes cap at 1 toward `support_count` regardless of quantity.
7. **Synthetic facts drift** — synthesized generalizations valid at promotion time can become stale. Add `valid_until` (90-day default for synthetic facts) and a re-validation job.
8. **Ze's design is ahead of all published production systems** — MemGPT, Mem0, A-MEM, and TiMem none implement adversarial critic-gated promotion. TiMem is the only system with offline consolidation; its documented failure (re-compressing summaries) is the hard ban Ze already has. Ze's staging buffer + provenance model is novel in the literature.
9. **Ze already has the right structural hooks** — `creation_method="synthesized"`, `reviewed` flag, `ProactiveScheduler`, and the `GoalSuggestionJob` read→synthesize→gate→push pattern are all reusable.

---

## Purpose

Ze runs a controlled offline memory improvement loop with four distinct phases:

```
Wake  →  Sleep (NREM)  →  Dream (REM)  →  Morning Integration
```

- **Wake:** Capture experiences with provenance and salience scores.
- **Sleep (NREM):** Replay important episodes, compress, deduplicate, and extract policy/skill patterns from session structure — no synthesis.
- **Dream (REM):** Generate novel variants, counterfactuals, perturbations, and plan stress-tests — all staged before any promotion.
- **Morning Integration:** Three-gate scoring pipeline + LLM critic validates staged artifacts; user reviews borderline cases; accepted outputs go to long-term memory; rejected outputs go to the forgetting/decay track; the journal surfaces what changed.

No phase writes synthetic outputs directly to live memory. All dream products live in a staging buffer until all gates pass and support thresholds are met, or until the user explicitly accepts, revises, or rejects them.

---

## Responsibilities

- Tag episodes with `replay_score`, `source`, and `has_sensitive_entity` at write time (Wake Phase hook).
- Schedule and run the Sleep and Dream passes on a nightly cron.
- Compress eligible raw episodes into session summaries (Sleep pass, extends existing archival).
- Extract policy/skill candidates directly from compressed session structure (Sleep pass, no LLM).
- Detect schema candidate clusters from overlapping episodes (Sleep pass, feeds Dream pass).
- Generate counterfactuals, perturbations, and plan stress-tests (Dream pass, staged).
- Run three-gate + two-call LLM critic pipeline over every staged artifact.
- Promote high-confidence, well-supported, temporally-diverse artifacts to long-term memory.
- Mark rejected or user-discarded artifacts for decay/forgetting.
- Write a dream journal entry per run, surfaced to the user in the morning briefing.
- Accept user approve/revise/reject decisions via REST API.
- Provide a per-run rollback endpoint that bulk-contradicts all promoted artifacts from a run.
- Exclude episodes tagged with sensitive entities from all dream passes.

---

## Out of Scope

- Generating synthetic episodes from scratch (no pure hallucination path).
- Re-summarizing already-summarized content (hard ban on `provenance=compressed` as source).
- Modifying LangGraph checkpoint state or conversation history.
- Real-time dreaming during active sessions.
- Emotional valence tagging (biological analogue exists; mechanism in software is unclear).
- Training or fine-tuning any model.
- BM25 + vector hybrid retrieval (identified gap from production system survey; deferred to a separate retrieval improvement phase).
- Re-validation job for stale synthetic facts (deferred to Phase 78b).

---

## Module Location

```
core/ze-memory/
  ze_memory/
    dream/
      __init__.py
      types.py          # DreamArtifact, DreamRun, ReplayCandidate, DreamJournalEntry
      scorer.py         # replay_score() — priority for episode selection (Wake hook)
      sleep_pass.py     # NREM: compress, dedup, decay, schema detection, policy extraction
      dream_pass.py     # REM: counterfactuals, perturbations, synthesis, stress-tests
      gates.py          # three pre-gates: NLI groundedness, novelty, retrievability
      critic.py         # LLM contradiction check (runs after all gates pass)
      promoter.py       # staging → long-term memory promotion + forgetting + rollback
      store.py          # PostgresDreamStore
      journal.py        # DreamJournalEntry builder + morning briefing hook
      job.py            # DreamJob(ProactiveJob)
```

---

## Memory Layer Model

```
─────────────────────────────────────────────────────────────
  WAKE PHASE
─────────────────────────────────────────────────────────────
  User interactions + tool outcomes
       │ episodic capture
       │ replay_score + source (ze_observed | user_asserted) tagged async at write
       │ sensitive entity check → episode.has_sensitive_entity
       ▼
┌─────────────────────────────────────────────────────┐
│  Short-Term Memory (Episodic Buffer)                │
│  memory_episodes — provenance=raw                   │
│  recent traces + provenance + replay_score + source │
└────────────┬────────────────────────────────────────┘
             │
─────────────────────────────────────────────────────────────
  SLEEP PHASE (NREM)  — no LLM calls
─────────────────────────────────────────────────────────────
             │
             ├─ [compress eligible sessions] ───────────────────►  memory_session_summaries
             │                                                       (provenance=compressed;
             │                                                        NEVER re-used as source)
             ├─ [dedup facts + decay unused episodes]
             │
             └─ [policy/schema candidate detection] ─────────────► Dream buffer
                  (entity overlap, recurring tool sequences)         (policy_candidate,
                  [skip episodes where has_sensitive_entity=True]     schema_candidate)

─────────────────────────────────────────────────────────────
  DREAM PHASE (REM)
─────────────────────────────────────────────────────────────

  Dream buffer ──► LLM synthesis (haiku) ──► staged artifact
                                                  │
                              ┌─── Gate 1: NLI groundedness (faithfulness ≥0.75)
                              ├─── Gate 2: embedding novelty (cosine <0.92 to existing facts)
                              └─── Gate 3: embedding retrievability (source episode in top-3)
                                          │ all three pass
                                          ▼
                    LLM critic Call A: challenge (sonnet, temperature=0.1)
                    LLM critic Call B: verify   (sonnet, temperature=0.3)
                    Both must PASS

─────────────────────────────────────────────────────────────
  MORNING INTEGRATION
─────────────────────────────────────────────────────────────

  All gates + both critics pass + support validation:
  (support_count≥3, distinct_sessions≥2, temporal_spread≥7d, user_asserted_count≤1)
  AND artifact_type != hindsight_fact
       │
       ├─ auto-promote ──► Long-Term Memory: Semantic (memory_facts, valid_until=+90d)
       │                   Long-Term Memory: Policy/Skill (memory_procedures)
       │                   (with dream_run_id + derived_from for rollback lineage)
       │
       ├─ needs_review → user sees dream journal
       │       ├─ approve ──► Long-Term Memory
       │       ├─ revise  ──► user edits → re-promoted with revised content
       │       └─ reject  ──► Forgetting track
       │
       └─ gates fail or either critic FAIL ──► Forgetting track
                                               (source episode retrieval_weight decremented)
       │
       Journal entry ──► morning briefing pull ──► User
       Rollback: POST /runs/{run_id}/rollback (bulk-contradicts run's promoted facts)
```

**Invariants:**
- `provenance=compressed` records are never source material for further synthesis.
- `provenance=synthetic` records never overwrite `provenance=raw` or `provenance=compressed`.
- Every `memory_dream_artifacts` row carries `source_episode_ids` — never empty.
- Episodes with `has_sensitive_entity=True` are excluded from all dream passes.
- Forgetting is always a `retrieval_weight` reduction first; hard archive only when `weight < 0.1`.
- `hindsight_fact` artifacts are never auto-promoted — always `needs_review` regardless of scores.

---

## Four-Phase Pipeline

### Phase 1 — Wake (episode write hook)

Runs during active sessions. Hooks into the existing `write_episode` path via `asyncio.create_task` to avoid adding latency to conversation turns.

**Steps:**
1. Tag `source`: `ze_observed` if the episode records Ze's inference from tool outputs, calendar/email data, or behavioral signals. `user_asserted` if the episode primarily records something the user stated directly.
2. Check linked entities: if any entity in the episode has `sensitive=True`, set `has_sensitive_entity=True`.
3. Compute `replay_score` (see Replay Score section).
4. Set `provenance = "raw"`.

---

### Phase 2 — Sleep Pass (NREM-like)

Runs first in the nightly job. No LLM synthesis calls. Pure reorganization.

**Steps:**
1. **Score refresh** — recompute `replay_score` for episodes since last run. Skip `has_sensitive_entity=True` episodes.
2. **Replay candidate selection** — top-K by `replay_score`; cap at `max_replay_episodes`. Increment `replay_count` and set `last_replayed_at`.
3. **Session compression** — sessions with ≥3 episodes older than `session_archive_threshold_days`: run existing `SessionSummariser`. Mark `archived=True`. `provenance=compressed` on summaries.
4. **Fact deduplication** — delegate to existing `MemoryConsolidator.dedup_facts()`.
5. **Decay pass** — episodes not selected for replay in `decay_cycles` consecutive runs: reduce `retrieval_weight` by `decay_rate`. When `retrieval_weight < forgetting_weight_threshold`: mark `archived=True`.
6. **Schema candidate detection** — clusters of ≥3 non-sensitive episodes sharing overlapping entities. Minimum: entity must appear in ≥3 distinct sessions (not just 3 episodes). Exclude sessions flagged `dream_influenced=True` from cluster membership unless the influencing artifact has been corroborated or rolled back. Write as `schema_candidate`. Cap: `max_schema_candidates_per_run`. No LLM call.
7. **Policy/skill candidate detection** — recurring tool sequences across ≥3 sessions. Exclude `dream_influenced` sessions same as above. Write as `policy_candidate`. No LLM call.

---

### Phase 3 — Dream Pass (REM-like)

Runs after Phase 2. All outputs staged in buffer. Generator uses haiku-class model.

**Steps:**
1. **Schema synthesis** — for each `schema_candidate`: LLM generates a generalized pattern from the cluster. Stage as `synthesized_insight`.
2. **Policy extraction** — for each `policy_candidate`: LLM generates a candidate procedure. Stage as `synthesized_procedure`.
3. **Hindsight relabeling** — for recently completed goals with failed milestones: LLM re-examines whether any failure produced a partial achievement. Stage as `hindsight_fact`. **Always** flagged `needs_review` — never auto-promoted.
4. **Plan stress-testing** — for active goals with open milestones and no progress in ≥3 days: LLM generates adversarial risk scenarios. Stage as `plan_stress_test`. Cap: `max_stress_tests_per_goal`.
5. **Counterfactuals and perturbation checks** — deferred to post-v1. Types exist in the enum for future use; `dream_pass.py` must not invoke them until the scoring integration is specified.
6. **Scoring pipeline** — for all promotable staged artifacts: run all three gates, then both LLM critic calls (see Scoring Pipeline section).

---

### Phase 4 — Morning Integration

Runs after Phase 3. Automated promotion + user review surface.

**Steps:**
1. **Support validation** — before any promotion:
   - `support_count >= auto_promote_min_support` (default 3)
   - distinct `session_id` count in `source_episode_ids >= 2`
   - temporal spread of source episodes `>= 7 days`
   - user-asserted episode count in source `<= 1`
   - `artifact_type != hindsight_fact`

2. **Auto-promotion** — all gates passed + both critic calls PASS + support validation passed:
   - `synthesized_insight` → `memory_facts` with `provenance="synthesized"`, `creation_method="synthesized"`, `reviewed=False`, `valid_until=now+90d`, `dream_run_id=run.id`, `derived_from=[source fact ids]`
   - `synthesized_procedure` → `memory_procedures` with `creation_method="synthesized"`, `dream_run_id=run.id`
   - `plan_stress_test` → `memory_procedures` as a risk heuristic, `dream_run_id=run.id`
   - Mark artifact `status=promoted`.

3. **Review queue** — artifacts that passed gates + critic but failed support validation, OR `hindsight_fact` type: mark `status=needs_review`.

4. **Forgetting** — artifacts that failed any gate or either critic call: mark `status=rejected`. Reduce `retrieval_weight` of source episodes by `decay_rate`.

5. **Synthetic fact confidence decay** — for each `memory_facts` row where `provenance='synthesized' AND corroborated=False`:
   - If `created_at` is more than 30 days ago: decrement `confidence` by 0.03 per dream run.
   - If `confidence < 0.50`: set `reviewed=False` (surfaces in memory review).
   - If `confidence < 0.25`: set `contradicted=True` (effectively expires it).
   - If a raw session episode since promotion contains the same claim (embedding cosine ≥ 0.88 to the fact): set `corroborated=True`, `last_corroborated_at=now()` — stops the decay clock permanently.
   This is the backstop for everything the critic missed: a promoted synthetic fact that is never reinforced by real observations gradually loses authority until it expires or the user confirms it.

6. **Session summary contamination tracking** — during retrieval in active sessions: if any `provenance='synthesized'` fact is retrieved and included in the LLM context, record its `dream_artifact_id` in `memory_session_summaries.dream_artifact_ids` for the current session. Set `dream_influenced=True`. These summaries are excluded from dream pass source selection until either: (a) user confirms the underlying fact in conversation, triggering `corroborated=True`, or (b) the source artifact is rolled back.

7. **Dream journal** — write `DreamJournalEntry`. Available for `BriefingJob` pull.

---

## Scoring Pipeline

Every promotable artifact passes through this pipeline in sequence. A failure at any step marks the artifact `rejected` and skips remaining steps.

```
artifact.content + source_episodes
         │
         ▼
 ┌─── Gate 1: NLI Groundedness ──────────────────────────────────────────┐
 │  Model: cross-encoder/nli-deberta-v3-small (~90MB, no API call)       │
 │  Method: decompose content into atomic sentences; NLI-score each      │
 │          against source episodes; faithfulness = supported / total    │
 │  Threshold: faithfulness_score >= 0.75                                │
 └───────────────────────────────────────────────────────────────────────┘
         │ pass
         ▼
 ┌─── Gate 2: Embedding Novelty ─────────────────────────────────────────┐
 │  Method: embed content; max cosine similarity to all existing         │
 │          promoted facts (provenance != 'synthesized' to avoid         │
 │          comparing against other dream outputs)                       │
 │  Threshold: max_cosine_sim < 0.92                                     │
 │  Fail → reject as duplicate of existing fact                          │
 └───────────────────────────────────────────────────────────────────────┘
         │ pass
         ▼
 ┌─── Gate 3: Embedding Retrievability ──────────────────────────────────┐
 │  Method: embed content; retrieve top-3 episodes from episode store;   │
 │          require at least 1 source episode in top-3 (or top-5 if     │
 │          support_count >= 5)                                          │
 │  Fail → reject as too abstract to be useful in retrieval             │
 └───────────────────────────────────────────────────────────────────────┘
         │ pass
         ▼
 ┌─── LLM Critic Call A: Challenge ──────────────────────────────────────┐
 │  Model: anthropic/claude-sonnet-4-5 (stronger than haiku generator)             │
 │  Temperature: 0.1                                                     │
 │  Framing: adversarial — "find every way this claim could be wrong,    │
 │           overstated, contradicted, or unsupported by the source"     │
 │  Extra: if claim contains negation, explicitly verify the negation    │
 │         is supported (negation blindness failure mode)                │
 │  Output: "PASS" or "FAIL: <one sentence reason>"                      │
 └───────────────────────────────────────────────────────────────────────┘
         │ PASS
         ▼
 ┌─── LLM Critic Call B: Verify ─────────────────────────────────────────┐
 │  Model: anthropic/claude-sonnet-4-5                                             │
 │  Temperature: 0.3                                                     │
 │  Framing: constructive — "verify each claim is traceable to a         │
 │           specific source episode; list any that lack a clear source" │
 │  Output: "PASS" or "FAIL: <citation gaps>"                            │
 └───────────────────────────────────────────────────────────────────────┘
         │ both PASS
         ▼
  Support validation (Phase 4, step 1)
         │
         ▼
  auto-promote or needs_review
```

**Why two critic calls:** A single framing exhibits sycophantic anchoring — the model tends to agree with whatever it just generated. Call A challenges aggressively; Call B verifies constructively. A claim that passes aggressive challenge but fails constructive verification is a plausible-sounding confabulation. Using sonnet-class (vs haiku generator) adds model diversity — the strongest known defense against shared-bias failure in LLM-as-judge settings.

**NLI model:** `cross-encoder/nli-deberta-v3-small` (~90MB, ~100ms/claim on CPU). Loaded as a second singleton in `gates.py` alongside Ze's existing embedding model. No API cost.

**Non-English episodes:** DeBERTa-v3-small is English-first. For non-English artifacts, fall back to an LLM-based groundedness check using the synthesis model.

---

## Data Structures

```python
# core/ze-memory/ze_memory/dream/types.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID


class ArtifactType(str, Enum):
    SCHEMA_CANDIDATE = "schema_candidate"           # Phase 2: entity cluster, no LLM
    POLICY_CANDIDATE = "policy_candidate"           # Phase 2: procedural pattern, no LLM
    SYNTHESIZED_INSIGHT = "synthesized_insight"     # Phase 3: generalised fact from schema
    SYNTHESIZED_PROCEDURE = "synthesized_procedure" # Phase 3: procedure from policy candidate
    HINDSIGHT_FACT = "hindsight_fact"               # Phase 3: always needs_review, never auto-promoted
    PLAN_STRESS_TEST = "plan_stress_test"           # Phase 3: adversarial risk scenario for active goal
    COUNTERFACTUAL = "counterfactual"               # Future: critic-only; never promoted
    PERTURBATION_CHECK = "perturbation_check"       # Future: critic-only; never promoted


class ArtifactStatus(str, Enum):
    PENDING = "pending"             # awaiting gates + critic
    CRITIC_ONLY = "critic_only"     # counterfactual / perturbation — not eligible for promotion
    PROMOTED = "promoted"           # accepted into long-term memory
    REJECTED = "rejected"           # failed gate/critic/support or user rejected
    NEEDS_REVIEW = "needs_review"   # passed all gates but below auto-promote threshold
    REVISED = "revised"             # user edited content, then promoted
    ROLLED_BACK = "rolled_back"     # rolled back via per-run rollback endpoint


@dataclass
class DreamArtifact:
    id: UUID
    run_id: UUID
    artifact_type: ArtifactType
    content: str
    source_episode_ids: list[UUID]              # raw episode UUIDs — never empty
    source_fact_ids: list[UUID]
    support_count: int
    distinct_session_count: int                 # distinct session_ids in source_episode_ids
    temporal_spread_days: int                   # days between earliest and latest source episode
    user_asserted_source_count: int             # source episodes tagged user_asserted
    faithfulness_score: Optional[float]         # Gate 1; None before scoring
    novelty_score: Optional[float]              # Gate 2 (1 - max_cosine_sim)
    retrievable: Optional[bool]                 # Gate 3
    critic_a_verdict: Optional[str]             # "PASS" | "FAIL"
    critic_a_reason: Optional[str]
    critic_b_verdict: Optional[str]             # "PASS" | "FAIL"
    critic_b_reason: Optional[str]
    status: ArtifactStatus
    user_revised_content: Optional[str]
    promoted_to: Optional[str]                  # "memory_facts" | "memory_procedures"
    promoted_id: Optional[UUID]
    created_at: datetime
    reviewed_at: Optional[datetime]


@dataclass
class DreamRun:
    id: UUID
    started_at: datetime
    finished_at: Optional[datetime]
    episodes_scored: int
    episodes_replayed: int
    artifacts_generated: int
    artifacts_promoted: int
    artifacts_rejected: int
    artifacts_pending_review: int
    sleep_pass_duration_ms: int
    dream_pass_duration_ms: int
    integration_duration_ms: int
    error: Optional[str]


@dataclass
class ReplayCandidate:
    episode_id: UUID
    replay_score: float
    recency_score: float
    novelty_score: float
    confidence_inverse_score: float


@dataclass
class DreamJournalEntry:
    run_id: UUID
    summary: str                      # LLM-generated 2–3 sentence narrative
    episodes_processed: int
    insights_promoted: int
    procedures_extracted: int
    plan_risks_surfaced: int
    pending_review: int
    created_at: datetime
```

---

## Database Schema

```sql
-- zm009

CREATE TABLE memory_dream_runs (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at                  TIMESTAMPTZ NOT NULL,
    finished_at                 TIMESTAMPTZ,
    episodes_scored             INT NOT NULL DEFAULT 0,
    episodes_replayed           INT NOT NULL DEFAULT 0,
    artifacts_generated         INT NOT NULL DEFAULT 0,
    artifacts_promoted          INT NOT NULL DEFAULT 0,
    artifacts_rejected          INT NOT NULL DEFAULT 0,
    artifacts_pending           INT NOT NULL DEFAULT 0,
    sleep_pass_duration_ms      INT,
    dream_pass_duration_ms      INT,
    integration_duration_ms     INT,
    error                       TEXT
);

CREATE TABLE memory_dream_artifacts (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                      UUID NOT NULL REFERENCES memory_dream_runs(id) ON DELETE CASCADE,
    artifact_type               TEXT NOT NULL,
    content                     TEXT NOT NULL,
    source_episode_ids          UUID[] NOT NULL DEFAULT '{}',
    source_fact_ids             UUID[] NOT NULL DEFAULT '{}',
    support_count               INT NOT NULL DEFAULT 0,
    distinct_session_count      INT NOT NULL DEFAULT 0,
    temporal_spread_days        INT NOT NULL DEFAULT 0,
    user_asserted_source_count  INT NOT NULL DEFAULT 0,
    faithfulness_score          FLOAT,
    novelty_score               FLOAT,
    retrievable                 BOOLEAN,
    critic_a_verdict            TEXT,
    critic_a_reason             TEXT,
    critic_b_verdict            TEXT,
    critic_b_reason             TEXT,
    status                      TEXT NOT NULL DEFAULT 'pending',
    user_revised_content        TEXT,
    promoted_to                 TEXT,
    promoted_id                 UUID,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at                 TIMESTAMPTZ
);

CREATE INDEX idx_dream_artifacts_run    ON memory_dream_artifacts(run_id);
CREATE INDEX idx_dream_artifacts_status ON memory_dream_artifacts(status);
CREATE INDEX idx_dream_artifacts_type   ON memory_dream_artifacts(artifact_type);

CREATE TABLE memory_dream_journal (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID NOT NULL REFERENCES memory_dream_runs(id),
    summary                 TEXT NOT NULL,
    episodes_processed      INT NOT NULL DEFAULT 0,
    insights_promoted       INT NOT NULL DEFAULT 0,
    procedures_extracted    INT NOT NULL DEFAULT 0,
    plan_risks_surfaced     INT NOT NULL DEFAULT 0,
    pending_review          INT NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Episode metadata side table (keeps memory_episodes immutable — source content never changes)
-- Mutable dream-phase fields live here; joined on episode_id at read time.
CREATE TABLE memory_episode_metadata (
    episode_id          UUID PRIMARY KEY REFERENCES memory_episodes(id) ON DELETE CASCADE,
    replay_score        FLOAT,
    last_replayed_at    TIMESTAMPTZ,
    replay_count        INT NOT NULL DEFAULT 0,
    retrieval_weight    FLOAT NOT NULL DEFAULT 1.0,
    provenance          TEXT NOT NULL DEFAULT 'raw',
    -- 'raw' | 'archived' (content intact; weight near 0)
    source              TEXT NOT NULL DEFAULT 'ze_observed',
    -- 'ze_observed' | 'user_asserted'
    has_sensitive_entity BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_episode_metadata_score  ON memory_episode_metadata(replay_score DESC NULLS LAST);
CREATE INDEX idx_episode_metadata_weight ON memory_episode_metadata(retrieval_weight);
CREATE INDEX idx_episode_metadata_source ON memory_episode_metadata(source);

-- Add provenance, validity window, rollback lineage, and decay tracking to facts
ALTER TABLE memory_facts
    ADD COLUMN provenance        TEXT NOT NULL DEFAULT 'raw',
    -- provenance values: 'raw' | 'synthesized'
    ADD COLUMN valid_until       TIMESTAMPTZ,
    -- NULL = never expires (raw facts); +90d for synthesized facts
    ADD COLUMN dream_run_id      UUID,
    -- set when promoted by a dream run; enables per-run rollback
    ADD COLUMN derived_from      UUID[] NOT NULL DEFAULT '{}',
    -- IDs of memory_facts used as synthesis inputs (one-hop lineage)
    ADD COLUMN corroborated      BOOLEAN NOT NULL DEFAULT FALSE,
    -- set TRUE when a raw episode endorses the same claim after promotion;
    -- stops the confidence decay clock
    ADD COLUMN last_corroborated_at TIMESTAMPTZ;
    -- timestamp of most recent raw corroboration event

-- Track which session summaries were contaminated by synthesized memory retrieval.
-- If any synthesized fact was retrieved during the session that produced a summary,
-- record the dream artifact IDs here. Summaries with non-empty dream_artifact_ids
-- are excluded from dream pass source selection until corroborated or rolled back.
ALTER TABLE memory_session_summaries
    ADD COLUMN dream_artifact_ids UUID[] NOT NULL DEFAULT '{}',
    ADD COLUMN dream_influenced   BOOLEAN NOT NULL DEFAULT FALSE;

-- Add sensitive flag to entities (blocks dreaming on linked episodes)
ALTER TABLE memory_entities
    ADD COLUMN sensitive BOOLEAN NOT NULL DEFAULT FALSE;
```

---

## Replay Score Function

```python
# core/ze-memory/ze_memory/dream/scorer.py

def replay_score(
    episode: Episode,
    now: datetime,
    existing_facts: list[Fact],
    max_age_days: float = 30.0,
) -> float:
    if episode.has_sensitive_entity:
        return 0.0   # excluded from dreaming entirely

    recency = max(0.0, 1.0 - (now - episode.created_at).days / max_age_days)
    confidence_inverse = 1.0 - episode.relevance   # weak memories score higher (SHY principle)
    novelty = _novelty_score(episode, existing_facts)
    access_inverse = 1.0 / (1.0 + episode.replay_count)

    # user-asserted episodes score lower to reduce provenance laundering risk
    source_weight = 0.5 if episode.source == "user_asserted" else 1.0

    return source_weight * (
        0.35 * recency
        + 0.25 * confidence_inverse
        + 0.25 * novelty
        + 0.15 * access_inverse
    )
```

---

## Morning Briefing Integration

`BriefingJob` (`ze_personal/jobs/`) pulls from `PostgresDreamStore.get_latest_journal_entry()` — not a push from `DreamJob`. This avoids adding a `ze_personal` → `DreamJob` import; `DreamStore` is a `ze_memory` interface already accessible to `ze_personal`.

If `pending_review > 0` or `insights_promoted > 0`, the briefing includes a "Ze dreamed" section:

```
Ze processed N episodes overnight.
  → M insights promoted to memory
  → K plan risks surfaced for [goal name]
  → J items ready for your review
```

Dream section omitted when both counts are zero.

Update CLAUDE.md package dep graph to show `ze_personal` → `ze_memory.dream.store` (read-only access to dream journal).

---

## REST API

```
GET  /api/v0/memory/dream/journal              # list recent DreamJournalEntry records
GET  /api/v0/memory/dream/artifacts            # list artifacts with status=needs_review
GET  /api/v0/memory/dream/artifacts/{id}       # get artifact detail + source episodes

POST /api/v0/memory/dream/artifacts/{id}/approve
     # triggers DreamPromoter.promote()

POST /api/v0/memory/dream/artifacts/{id}/reject
     # marks rejected; source episode retrieval_weight decremented

POST /api/v0/memory/dream/artifacts/{id}/revise
     body: { "content": "user-edited version of the claim" }
     # sets user_revised_content, status=revised, re-runs promotion with revised content

POST /api/v0/memory/dream/runs/{run_id}/rollback
     # bulk-marks all artifacts from run as rolled_back;
     # marks all memory_facts with dream_run_id=run_id as contradicted;
     # flags all facts in derived_from chains for re-evaluation (needs_review on memory_facts);
     # sets needs_resummary=True on all memory_session_summaries where dream_artifact_ids
     #   contains any artifact from this run (clears contaminated summaries)
```

---

## Configuration

```yaml
# config/config.yaml
dream:
  enabled: true
  cron: "0 3 * * *"
  max_replay_episodes: 100
  max_synthesis_per_run: 20
  max_stress_tests_per_goal: 2
  max_schema_candidates_per_run: 30        # prevent O(n^2) entity cluster explosion
  session_archive_threshold_days: 7
  auto_promote_min_support: 3
  auto_promote_min_distinct_sessions: 2
  auto_promote_min_temporal_spread_days: 7
  auto_promote_max_user_asserted: 1
  nli_groundedness_threshold: 0.75
  novelty_similarity_threshold: 0.92       # reject if max cosine > this (duplicate)
  decay_cycles: 5
  decay_rate: 0.1
  forgetting_weight_threshold: 0.1
  synthesis_model: "anthropic/claude-haiku-4-5"
  critic_model: "anthropic/claude-sonnet-4-5"  # intentionally stronger than synthesis_model
  synthetic_fact_valid_days: 90
```

---

## Integration Points

### Job wiring (`ze_api/compose.py`)

```python
def register_dream_jobs(
    scheduler: ProactiveScheduler,
    settings: ZeApiSettings,
    shared: SharedServices,
) -> None:
    if settings.dream.enabled:
        scheduler.add_cron_job(
            fn=shared.dream_job.run,
            cron=settings.dream.cron,
            job_id="dream_memory",
        )
```

### DI wiring (`ze_api/container.py`)

```python
self.dream_store = PostgresDreamStore(pool=self.db_pool)
self.dream_job = DreamJob(
    memory_store=self.memory_store,
    dream_store=self.dream_store,
    client=self.llm_client,
    settings=self.settings.dream,
    notifier=self.notifier,
)
```

### Episode write hook (`ze_memory/store.py`)

```python
# fire-and-forget to avoid latency impact on conversation turns
asyncio.create_task(_tag_episode(episode, recent_facts))
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_memory.store` | Read episodes, facts, procedures; write promoted artifacts |
| `ze_memory.consolidator` | Reuse `dedup_facts()`, `archive_session_episodes()` in Sleep pass |
| `ze_agents.client` | LLM calls for synthesis and critique |
| `ze_proactive.job` | `ProactiveJob` protocol |
| `ze_proactive.scheduler` | `add_cron_job()` |
| `ze_proactive.notifier` | Push morning briefing with dream summary |
| `cross-encoder/nli-deberta-v3-small` | Gate 1 NLI groundedness — singleton in `gates.py` |

---

## Implementation Sequence

### Step 0 — Foundation
- [ ] Migration zm009: all new columns on `memory_episodes`, `memory_facts`, `memory_entities`; create dream tables
- [ ] Dataclasses in `types.py`
- [ ] `PostgresDreamStore` CRUD + `get_latest_journal_entry()`

### Step 1 — Wake Hook
- [ ] `replay_score()` in `scorer.py` with sensitive entity check and source weight
- [ ] `_classify_source()`: default `ze_observed`; mark `user_asserted` only when episode has no tool call outcomes
- [ ] Wire into `write_episode()` as `asyncio.create_task`
- [ ] Mark `sensitive=True` on `memory_entities` for: financial entities, credentials, health-related entities

### Step 2 — Sleep Pass
- [ ] `SleepPass.run()`: score refresh, episode selection (skip sensitive), session compression (delegate), fact dedup (delegate), decay, schema/policy candidate detection
- [ ] Schema candidates require ≥3 distinct sessions; cap at `max_schema_candidates_per_run`
- [ ] Tests: verify sensitive episode exclusion and candidate detection

### Step 3 — Scoring Pipeline + Dream Pass
- [ ] `gates.py`: load `nli-deberta-v3-small` singleton; implement Gates 1, 2, 3
- [ ] Non-English fallback for Gate 1: use haiku model for groundedness check
- [ ] `DreamPass.run()`: schema synthesis, policy extraction, hindsight relabeling (always `needs_review`), plan stress-tests
- [ ] `DreamCritic.critique_artifact()`: two sequential calls (Call A challenge, Call B verify); negation-aware prompts; both must pass
- [ ] Tests: mock LLM + NLI model; verify gate rejection paths and two-call critic logic

### Step 4 — Morning Integration + Promoter
- [ ] `DreamPromoter.promote()`: support validation (session diversity, temporal spread, user-asserted cap), auto-promote, needs-review flagging, forgetting track
- [ ] `DreamPromoter.apply_user_decision()`: approve/reject/revise
- [ ] `DreamPromoter.rollback_run()`: bulk-mark + contradict + flag derived_from chains
- [ ] Write facts with `valid_until`, `dream_run_id`, `derived_from`, `provenance="synthesized"`, `corroborated=False`
- [ ] Confidence decay step: on each morning integration run, decrement `confidence` on non-corroborated synthetic facts older than 30 days; expire at < 0.25
- [ ] Corroboration detection: in `write_episode()`, after storing the episode, check for any `provenance='synthesized'` facts with cosine ≥ 0.88 to the episode embedding — mark `corroborated=True` on matches
- [ ] Session contamination tracking: in `retrieve()` path, when a `provenance='synthesized'` fact is fetched for context, record its `dream_artifact_id` in the current session's summary record
- [ ] Rollback: additionally set `needs_resummary=True` on contaminated session summaries
- [ ] **LAUNCH-BLOCKING**: verify `PostgresMemoryStore.retrieve()` filters `retrieval_weight > forgetting_weight_threshold`
- [ ] **LAUNCH-BLOCKING**: verify graph context fetch adds hedging for `provenance="synthesized"` facts ("Ze inferred this from a pattern")
- [ ] **LAUNCH-BLOCKING**: verify `hindsight_fact` is hardcoded to `needs_review` regardless of scores

### Step 5 — Journal + Briefing Hook
- [ ] `DreamJournal.write_entry()`
- [ ] `BriefingJob` pull integration (read-only, no DreamJob import)
- [ ] REST endpoints; update CLAUDE.md dep graph for `ze_personal` → `ze_memory.dream.store`
- [ ] Set job timeout on `DreamJob` to prevent indefinite runs

### Step 6 — Job Wiring
- [ ] `DreamJob(ProactiveJob)` orchestrates Sleep → Dream → Integration → Journal
- [ ] Wire into `compose.py` and `container.py`
- [ ] `dream` section in `config.yaml`

---

## Open Questions

- [x] **Three-gate pipeline.** Decision: NLI Gate (faithfulness ≥0.75) + Novelty Gate (cosine <0.92) + Retrievability Gate, then two adversarial LLM calls at sonnet-class. Binary PASS/FAIL is sufficient for v1 when gates handle groundedness.
- [x] **Provenance enforcement.** Decision: `provenance` column on `memory_facts` in zm009.
- [x] **Critic model.** Decision: `anthropic/claude-sonnet-4-5` for critic vs haiku for generator — intentional model diversity.
- [x] **`support_count` independence.** Decision: require distinct_sessions ≥2 AND temporal_spread ≥7d AND user_asserted_count ≤1.
- [ ] **First release scope:** Recommendation: Sleep pass + gates infrastructure in 78a. Dream pass (synthesis) in 78b. Validate episode selection and sensitive-entity tagging before adding LLM synthesis.
- [ ] **`_classify_source()` precision:** Heuristic needs tuning. Start conservative — only mark `user_asserted` when no tool call outcomes in episode.
- [ ] **NLI model language coverage:** DeBERTa-v3-small is English-first. Non-English fallback (LLM-based groundedness) needed before shipping to multilingual users.
- [ ] **Re-validation job for stale synthetic facts:** Query `memory_facts WHERE provenance='synthesized' AND valid_until < now()` and flag for re-evaluation. Design deferred to Phase 78b.
- [ ] **Inactivity trigger:** Deferred; cron sufficient for v1.
- [ ] **Source quality audit:** Before shipping Phase 78b (synthesis), audit current `memory_facts` quality. Dream quality is bounded by source episode quality.

---

## Failure Modes and Mitigations

| Failure Mode | Mitigation |
|---|---|
| Synthetic memory treated as fact | Staging buffer + `provenance="synthesized"` + hedging in graph context fetch |
| Self-confirming belief cluster | Session diversity (≥2) + temporal spread (≥7d) requirements; audit query detects post-hoc |
| Provenance laundering via user assertions | `source=user_asserted` tag; reduced replay_score; cap at 1 toward support_count |
| Haiku critic too permissive on plausible-but-unsupported claims | Three non-LLM pre-gates catch most false promotions before LLM critic runs |
| Single critic call fooled by fluency or sycophancy | Two independent calls with different framings (challenge vs verify); both must pass |
| Negation blindness in critic | Explicit negation-aware clause in both critic prompts |
| Re-summarizing summaries | Hard ban: `provenance=compressed` never used as source material |
| hindsight_fact overstating achievement | Type hardcoded to `needs_review`; user approval required regardless of scores |
| PII/sensitive data in dream pipeline | `sensitive=True` on entities; `has_sensitive_entity=True` episodes excluded entirely |
| Cost blowup | `max_synthesis_per_run` + `max_stress_tests_per_goal` + `max_schema_candidates_per_run` caps; haiku generator |
| No recovery path for wrong promoted fact | `dream_run_id` + `derived_from` lineage on every promoted fact; rollback endpoint |
| Morning briefing noise | Dream section omitted when both `insights_promoted` and `pending_review` are zero |
| `retrieval_weight` stored but not enforced | Verify retrieve() before shipping Sleep pass (launch-blocking) |
| Synthetic fact hedging absent | Verify graph context fetch hedges `provenance="synthesized"` (launch-blocking) |
| Schema candidate cluster explosion | `max_schema_candidates_per_run` cap + cluster requires ≥3 distinct sessions |
| `BriefingJob` hidden dep on `DreamJob` | Briefing is a pull from `DreamStore` interface only; update CLAUDE.md dep graph |
| Stale synthetic facts persisting | `valid_until=+90d` + gradual confidence decay (0.03/run after 30d); corroboration stops decay |
| Synthesized fact laundered via session summary | `dream_influenced=True` + `dream_artifact_ids` on summaries; excluded from source pool until corroborated or rolled back |
| Rollback leaving residue in session summaries | Rollback endpoint additionally sets `needs_resummary=True` on all `dream_influenced` summaries citing the rolled-back artifact |
