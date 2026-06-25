# Phase 79 — NLI Cross-Encoder Integration

**Status:** Done
**Depends on:** Phase 78a (shares the `cross-encoder/nli-deberta-v3-small` singleton)
**Packages touched:** `core/ze-memory`, `core/ze-correlation` (correlation grounding)

---

## What this is

Ze's memory layer currently uses only cosine similarity (bi-encoder MiniLM) for
comparing text — in deduplication, contradiction detection, and retrieval ranking.
Cosine similarity measures topical proximity, not logical relationship: two facts
like "João eats healthy" and "João never eats vegetables" may score ~0.72 cosine
(below any merge threshold) but are semantically contradictory.

This phase integrates `cross-encoder/nli-deberta-v3-small` (~90 MB local model,
shared with the Phase 78b dream gate) into three memory-layer callsites where
semantic judgment matters more than topical proximity.

The model is a `sentence-transformers` cross-encoder: given a `(premise, hypothesis)`
pair it returns logits for `[contradiction, neutral, entailment]`. Softmax gives
probabilities; we use those directly.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Model | `cross-encoder/nli-deberta-v3-small` | ~90 MB local, no API cost, same model as Phase 78b Gate1_NLI — one download, shared singleton |
| Singleton location | `core/ze-memory/ze_memory/nli.py` | Memory package owns it; 78b loads from the same location |
| Loading | Lazy-loaded at first call; cached via module-level `_model` | Consistent with `ze_core/embeddings.py` pattern |
| Language fallback | Skip NLI, fall back to cosine-only behaviour for non-Latin scripts | DeBERTa is English-primary; multilingual coverage is a Phase 79+ concern |
| Async execution | `asyncio.get_event_loop().run_in_executor(None, ...)` — CPU-bound inference off the event loop | Consistent with how the embedder is used in consolidation |
| Thresholds | `contradiction_nli ≥ 0.60`, `entailment_nli ≥ 0.70` | Calibrated to DeBERTa-v3-small outputs; configurable via `memory_config` |

---

## Callsite 1 — Contradiction detection in `dedup_facts()`

**File:** `core/ze-memory/ze_memory/consolidator.py`

### Current behaviour

`MemoryConsolidator.dedup_facts()` runs an O(n²) cosine loop over all active facts:

- cosine ≥ `MERGE_SILENT_THRESHOLD` (0.95): auto-merge (keep highest-confidence fact)
- cosine ≥ `MERGE_LLM_THRESHOLD` (0.85): LLM merge call
- cosine < 0.85: **not checked at all** — contradictions in this range are invisible

The LLM merge call (`_llm_merge`) costs ~1 haiku call per pair. For pairs in the
0.85–0.95 range the LLM is asked to merge two facts into one; it does not detect
contradictions.

### Problem

Two contradictory facts (e.g., "User is vegetarian" / "User eats meat at least once
a week") often score 0.70–0.84 cosine — below the LLM merge threshold. They survive
dedup indefinitely, polluting all downstream retrieval. Additionally, the LLM merge
call cannot reliably distinguish merge-worthy paraphrases from contradictions.

### Change

Add an NLI pass in the gap range and replace the LLM merge call's contradiction
detection with NLI:

```
cosine ≥ 0.95  → silent merge (unchanged)
cosine ≥ 0.85  → NLI classify:
                   NLI contradiction ≥ 0.60 → mark both contradicted; keep max(created_at)
                   NLI entailment    ≥ 0.70 → paraphrase → LLM merge (existing path)
                   NLI neutral             → skip (unchanged)
0.60 ≤ cosine < 0.85 → NLI classify:
                   NLI contradiction ≥ 0.60 → mark both contradicted; keep max(created_at)
                   otherwise               → skip
cosine < 0.60  → skip (unchanged)
```

The lower bound `0.60` prevents NLI from running on unrelated fact pairs — at <0.60
cosine the chance of semantic contradiction is negligible and the O(n²) NLI overhead
would dominate. The upper `0.85` boundary replaces the LLM merge trigger with a
cheaper, more precise NLI pre-filter.

**Conflict resolution rule:** When NLI detects contradiction, use `max(created_at)` —
keep the newer fact, contradict the older. Never use LLM judgment for conflict
resolution (same rule as Phase 78b).

**Batch efficiency:** Collect all NLI pairs that need classification in the inner loop
before calling the model. Then run `model.predict(pairs)` once per outer-loop row's
batch rather than one call per pair.

**New config keys** (added to `memory_config`):

```yaml
nli_contradiction_threshold: 0.60    # minimum contradiction prob to act
nli_entailment_threshold: 0.70       # minimum entailment prob to confirm paraphrase
nli_lower_cosine_bound: 0.60         # skip NLI if cosine below this
```

---

## Callsite 2 — Semantic contradiction check at write time

**File:** `core/ze-memory/ze_memory/retriever.py`
**Method:** `_write_fact_with_contradiction_check()` (line 544)

### Current behaviour

```python
# current: exact (predicate, subject_id) match only
existing = await conn.fetchrow(
    "SELECT id FROM memory_facts WHERE predicate=$1 AND subject_id=$2 AND contradicted=false",
    fact.predicate, fact.subject_id
)
if existing:
    await conn.execute("UPDATE memory_facts SET contradicted=true WHERE id=$1", existing["id"])
```

This fires only when the new fact shares both the same `predicate` string AND the
same `subject_id`. A fact written with `predicate="diet"` does not contradict one
written with `predicate="eating habits"` even if they say opposite things.

### Change

After the new fact is embedded (it already is, just before `_write_fact_with_contradiction_check`
is called), run a narrow semantic search for potentially-contradicting existing facts:

1. Fetch the top-10 most similar existing facts for the same `subject_id` using
   `embedding <=> $1::vector LIMIT 10` (ANN, not full scan).
2. For each candidate with cosine ≥ `nli_lower_cosine_bound`, run NLI.
3. If `contradiction ≥ nli_contradiction_threshold`: mark existing fact
   `contradicted=true`; keep the new fact. Log at DEBUG.
4. The current exact-match branch remains as a fast path before the NLI check.

**Constraint:** This runs on the write path. Steps:
- ANN vector search: ~2ms (pgvector, indexed)
- NLI inference for ≤10 pairs: ~15–50ms (DeBERTa-v3-small CPU, batched)
- Total write-path overhead: ~20–55ms per fact write

This is acceptable because `write_episode()` is fire-and-forget (already wrapped in
`asyncio.create_task()`), and `propose_facts()` is called at end-of-turn, not on the
critical response path.

If write-path latency becomes a concern, defer the NLI check to the nightly
consolidation pass instead (controlled by `nli_write_time_check: true` config flag,
default true).

---

## Callsite 3 — Retrieval re-ranking

**Files:** `core/ze-memory/ze_memory/retriever.py`, `core/ze-memory/ze_memory/policies.py`

### Current behaviour

All retrieval policies (`CompanionPolicy`, `ResearchPolicy`, `GoalsPolicy`, and
the `search_session_summaries` method) return results ordered by pure cosine
similarity (`embedding <=> query_embedding`). The bi-encoder (MiniLM) excels at
recall but not precision: it can retrieve topically related content that is not
actually relevant to the specific query.

### Change

Add an optional two-stage retrieval mode:

**Stage 1 (recall — unchanged):** Fetch top-K candidates using existing cosine ANN
(K = 2× current limit to give the re-ranker a wider candidate pool).

**Stage 2 (precision — new):** For each candidate text, run NLI with the query as
hypothesis and the candidate as premise. Score = `entailment_prob + 0.5 * neutral_prob`.
Re-sort candidates by this score. Return top-N (N = original limit).

This scores a candidate highly if it "supports" (entails or is consistent with) what
the user is asking, not just if it shares keywords.

**Where to add the re-rank call:**

- `PostgresMemoryStore.retrieve()` — re-rank `facts` and `session_summaries` after
  fetching, before budgeting. Episodes are already trimmed by token budget; re-rank
  the raw rows before budget trimming.
- `PostgresMemoryStore.search_session_summaries()` (line 523) — re-rank before
  returning.
- Policies do not change — they stay as pure SQL fetch layers; re-ranking lives in the
  store.

**Configuration:**

```yaml
nli_retrieval_rerank: true           # toggle (default true in 79b, false in 79a)
nli_rerank_candidate_multiplier: 2   # fetch K×2 candidates, return top K after rerank
nli_rerank_min_candidates: 5         # skip rerank if fewer than this many candidates
```

**Performance:**
- A typical retrieval fetches 30–50 candidates. At 2× multiplier: 60–100 pairs.
- DeBERTa-v3-small: ~5ms per pair on CPU → 300–500ms for 60–100 pairs.
- This is **not** acceptable on the request path. The `fetch_context` graph node
  runs before the agent call but the response cannot be delayed by 300ms.

**Mitigation:** Run re-ranking asynchronously — fetch results synchronously as today
(stage 1 cosine), dispatch stage-2 NLI in `asyncio.create_task()`, and write the
re-ranked order to a short-lived `memory_retrieval_cache` table. On the *next* request
in the same session, use the cached re-ranked order instead of fresh cosine ordering.
Sessions are long-lived (multiple turns), so by turn 2 the re-ranker has already run.
Turn 1 falls back to cosine; turns 2+ use NLI-ranked order.

Alternatively (simpler for v1): restrict re-ranking to `search_session_summaries()`
only, which is called by agents mid-execution (not on the hot response path), and
leave `retrieve()` on cosine for now. This trades precision for latency predictability.

**Phase split for this callsite:**
- **79a:** Re-rank `search_session_summaries()` only (called by agents mid-execution,
  latency less critical).
- **79b:** Full session-cached re-ranking for `retrieve()` with the async approach.

---

## Callsite 4 — Correlation hypothesis grounding

**File:** `core/ze-memory/ze_memory` (correlation push module — `ze_correlation/push.py`)
**Context:** Phase 57 `CorrelationEngine` generates hypotheses from episodic signal
co-occurrence. `SurfacingGate.check_push()` gates whether a hypothesis reaches the user.

### Current behaviour

`is_novel` in `check_push()` is computed by `ze_correlation/push.py` line 133:
cosine similarity to recent pushes > `novelty_similarity_max=0.85` → not novel.
The gate has no check for whether the evidence actually *supports* the hypothesis —
it checks confidence score, evidence count, and novelty, but those are all derived
from the correlation signal, not from semantic entailment of the hypothesis by
the supporting episodes.

### Change

Add a lightweight grounding check before `check_push()`:

```python
def _nli_grounded(hypothesis: str, evidence_summaries: list[str], nli_model) -> float:
    """Returns fraction of evidence that NLI-entails the hypothesis."""
    if not evidence_summaries:
        return 0.0
    pairs = [(e, hypothesis) for e in evidence_summaries]
    scores = nli_model.predict(pairs)  # shape: (N, 3) [contradiction, neutral, entailment]
    entailment_probs = softmax(scores, axis=1)[:, 2]
    return float(entailment_probs.mean())
```

Gate rule: if `_nli_grounded() < nli_grounding_threshold` (default 0.3), suppress the
push — the evidence does not actually support the hypothesis at text level. This
catches spurious correlations (two topics that co-occur but whose episode text doesn't
actually link them).

**This is a pre-filter before `check_push()`, not a replacement.** All existing
`check_push()` conditions still apply.

**Config:**

```yaml
nli_grounding_threshold: 0.30   # minimum average entailment fraction across evidence
```

**When to apply:** Push path only (unsolicited notifications). Inline surfacing
(`check_inline()`) is already user-initiated and has lower stakes — skip grounding
there.

---

## NLI model singleton

**File:** `core/ze-memory/ze_memory/nli.py` (new)

```python
from __future__ import annotations
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers.cross_encoder import CrossEncoder

_NLI_MODEL_ID = "cross-encoder/nli-deberta-v3-small"
_model: "CrossEncoder | None" = None


def get_nli_model() -> "CrossEncoder":
    global _model
    if _model is None:
        from sentence_transformers.cross_encoder import CrossEncoder
        _model = CrossEncoder(_NLI_MODEL_ID)
    return _model


def nli_scores(pairs: list[tuple[str, str]]) -> list[dict]:
    """Returns list of {contradiction, neutral, entailment} dicts for each pair."""
    import numpy as np
    from scipy.special import softmax

    model = get_nli_model()
    raw = model.predict(pairs)
    probs = softmax(raw, axis=1)
    return [
        {"contradiction": float(p[0]), "neutral": float(p[1]), "entailment": float(p[2])}
        for p in probs
    ]
```

Phase 78b's `Gate1_NLI` imports from this same module — one download, one warm-up.

**Language detection for fallback:**

```python
def _is_latin(text: str) -> bool:
    """Heuristic: at least 80% of word chars are ASCII."""
    chars = [c for c in text if c.isalpha()]
    return not chars or sum(1 for c in chars if ord(c) < 128) / len(chars) >= 0.8
```

If either side of a pair is non-Latin, skip NLI and use cosine-only behaviour.

---

## Database migrations

**79a:** No schema changes. The `provenance` and conflict columns added by Phase 78a's
zm009 migration are referenced (NLI uses the same `mark_contradicted()` path), but no
new tables or columns are needed.

**79b (Step 7 — full `retrieve()` re-ranking):** The async session-cached approach
requires a short-lived cache table. Migration `zm010`:

```sql
CREATE TABLE memory_retrieval_cache (
    session_id          TEXT NOT NULL,
    query_hash          TEXT NOT NULL,
    fact_ranked_ids     UUID[] NOT NULL DEFAULT '{}',
    summary_ranked_ids  UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, query_hash)
);

CREATE INDEX idx_retrieval_cache_session ON memory_retrieval_cache(session_id);
```

Rows are expired by the nightly dream job (`DreamJob` deletes where `created_at < now() - interval '1 day'`).
Implemented in `ze_memory/retrieval_cache.py` and `ze_memory/retrieval_rerank.py`.

---

## Dependency addition

Add to `core/ze-memory/pyproject.toml`:

```toml
"sentence-transformers>=2.7.0",   # already present for Phase 78b; confirm version
```

If `sentence-transformers` is already a dependency (it is from Phase 78b), no change
needed. The NLI cross-encoder model download is handled at startup in the same Docker
step as the Phase 78b model.

---

## Implementation sequence

### 79a — Contradiction detection (no latency risk)

Both callsites run off the hot response path:
- `dedup_facts()` is nightly
- `_write_fact_with_contradiction_check()` is fire-and-forget

**Step 1 — NLI singleton**

`core/ze-memory/ze_memory/nli.py` — add `get_nli_model()` and `nli_scores()`.
Add `_is_latin()` guard.

**Step 2 — Dedup NLI integration**

`core/ze-memory/ze_memory/consolidator.py`:
- Add NLI pass for pairs in `0.60 ≤ cosine < 0.95` range
- Contradiction → `mark_contradicted(older_id)` using `max(created_at)` rule
- Entailment (cosine ≥ 0.85) → existing `_llm_merge()` path (NLI confirms it's a paraphrase)
- Run NLI batch per outer-loop iteration

**Step 3 — Write-time NLI check**

`core/ze-memory/ze_memory/retriever.py` (`_write_fact_with_contradiction_check()`):
- After existing exact-match fast path
- ANN fetch top-10 same-subject facts
- NLI on pairs with cosine ≥ 0.60
- Mark contradicted on hit

**Step 4 — Tests**

`core/ze-memory/tests/`:
- `test_nli.py` — singleton loads, `nli_scores()` returns correct shape, `_is_latin()` guard
- `test_consolidator_nli.py` — contradictory fact pair (low cosine) is caught; paraphrase pair (same range, entailment) triggers LLM merge; unrelated pair (< 0.60 cosine) is skipped
- `test_store_nli.py` — write-time check catches contradictions that exact-match misses

### 79b — Retrieval re-ranking

**Step 5 — Re-rank `search_session_summaries()`**

`core/ze-memory/ze_memory/retriever.py`:
- After cosine fetch, if ≥ `nli_rerank_min_candidates`: run NLI re-rank
- Use `asyncio.get_event_loop().run_in_executor(None, ...)` to keep off event loop

**Step 6 — Correlation grounding**

`core/ze-correlation/ze_correlation/push.py`:
- Add `_nli_grounded()` pre-filter on push path only

**Step 7 — Full `retrieve()` re-ranking** ✅

Async session-cached re-ranking for `PostgresMemoryStore.retrieve()` in
`ze_memory/retriever.py`:

- Turn 1: policy cosine fetch (no added latency).
- Background: `build_retrieval_cache()` fetches `K × multiplier` candidates, NLI-reranks,
  upserts to `memory_retrieval_cache`.
- Turn 2+ (same `session_id` + `query_hash`): facts and session summaries replaced from
  cached ID order via `fetch_facts_by_ids` / `fetch_summaries_by_ids`, then re-budgeted.
- Excluded modules: `profile`, `memory_ui`, `planner`, `tool_executor`.

---

## Open questions

1. **Model availability in Docker:** Shipped — `apps/ze-api/Dockerfile` pre-downloads
   MiniLM and `cross-encoder/nli-deberta-v3-small` at build time. Phase 78b's
   `Gate1_NLI` imports from `ze_memory/nli.py` (one singleton, one warm-up).

2. **Portuguese coverage:** `_is_latin()` passes for Portuguese (é, ã, ç are Latin
   characters; the heuristic counts ASCII alpha chars, and most Portuguese text is
   ≥80% ASCII). DeBERTa-v3-small has weaker Portuguese accuracy than English (~80% vs
   ~92% on NLI benchmarks). Contradiction detection still works at the 0.60 threshold
   but expect ~10–15% more false-negatives on Portuguese fact pairs. Acceptable for v1;
   a multilingual cross-encoder (`cross-encoder/mDeBERTa-v3-base-xnli-multilingual`)
   is the upgrade path if precision becomes an issue.

3. **`nli_write_time_check` kill switch:** If write-path overhead proves > 100ms in
   production, flip `nli_write_time_check: false` to move the check entirely to the
   nightly consolidation pass.
