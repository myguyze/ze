# Phase 5 — Memory Consolidation Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| MemoryConsolidator — dedup, expiry, archive | ✅ Done |
| Migration 004 — expires_at + is_archive columns | ✅ Done |
| ConsolidationScheduler — nightly APScheduler job | ✅ Done |
| REST API — POST /memory/consolidate | ✅ Done |
| Digest extension — expiring_facts list | ✅ Done |
| Config — consolidation thresholds in config.yaml | ✅ Done |

---

## Purpose

As Ze accumulates user facts and interaction episodes over time, the memory store
degrades in quality: near-duplicate facts dilute retrieval precision, stale unreviewed
facts consume token budget, and the episodes table grows without bound. Phase 5
introduces a background consolidation job that runs nightly to clean up all three
problems. Every destructive action is soft-first — users see what is about to be
deleted before it is gone.

---

## Out of Scope

- Multi-episode narrative summarisation (building a continuous autobiography) — deferred.
- Cross-user memory (single-user system).
- Proactive Telegram notifications when consolidation runs.
- LLM-assisted expiry judgement (purely rule-based in Phase 5).
- Backfilling embeddings for raw episodes that were stored before Phase 2.

---

## Three Consolidation Tasks

### 1. Fact Deduplication

Find near-duplicate facts and merge them. Two facts are candidates if their embeddings
exceed the configured similarity threshold. Merging strategy is tiered by confidence:

| Similarity | Action |
|------------|--------|
| > `merge_silent_threshold` (default 0.95) | Silent merge — keep the newest fact, mark the older one `contradicted=true`. No LLM call. |
| `merge_llm_threshold`–`merge_silent_threshold` (default 0.85–0.95) | LLM merge — Haiku produces a single synthesised value from both. Insert as new fact, mark both originals `contradicted=true`. |
| < `merge_llm_threshold` | No action — dissimilar enough to coexist. |

**Reviewed facts are never auto-merged.** If either fact in a candidate pair has
`reviewed=true`, skip the pair and log it. A reviewed fact represents explicit user
confirmation; merging it silently would violate the editorial contract.

Facts marked `contradicted=true` by the merger are cleaned up by the expiry task
(see below) after the configured TTL.

### 2. Fact Expiry

Three rules, applied in order per consolidation run:

| Rule | Condition | Action |
|------|-----------|--------|
| **Grace delete** | `expires_at IS NOT NULL AND expires_at < NOW()` | Hard-delete. Grace period has elapsed. |
| **Contradicted cleanup** | `contradicted = true AND updated_at < NOW() - contradicted_ttl_days` | Hard-delete. Actively wrong, just clutter. |
| **Stale unreviewed** | `reviewed = false AND updated_at < NOW() - unreviewed_ttl_days AND expires_at IS NULL` | Soft-expire: set `expires_at = NOW() + expiry_grace_days`. |

`reviewed = true` facts are **never** automatically expired. The user explicitly
confirmed them; they are permanent until the user rejects them via `POST /memory/facts/review`.

Soft-expired facts appear in `GET /memory/digest` under `expiring_facts`. The user
can save a fact before its grace period ends by sending a `confirm` action — this
sets `reviewed = true` and clears `expires_at`.

### 3. Episode Archival

Raw episodes are retained in full within a recency buffer (default: last 14 days).
Anything older is a candidate for archival. Archival batches must reach a minimum
size before firing to avoid creating tiny archive rows.

**Algorithm per consolidation run:**

1. Count episodes where `created_at < NOW() - episode_recency_days AND is_archive = false`.
2. If count < `episode_min_archive_batch`, skip — not enough material.
3. Take the oldest `episode_archive_batch` (default 20) rows.
4. Compute the mean embedding across the batch.
5. Assemble a summarisation prompt from each episode's `summary` (or first 200 chars of
   `response` where `summary IS NULL`) and call Haiku.
6. Insert one new `episodes` row: `is_archive = true`, `agent = '__archive__'`,
   `prompt = "Archive of N episodes ({start_date} to {end_date})"`,
   `response` = Haiku summary, `embedding` = mean embedding.
7. Hard-delete the raw episode rows.
8. Repeat from step 3 until fewer than `episode_min_archive_batch` unarchived episodes
   remain outside the recency buffer.

Archive rows surface in `GET /memory/digest` under `recent_episodes` like any other
episode — the retrieval path in `MemoryStore._load_episodes` is unchanged because
archive rows have embeddings and a summary already set.

If the Haiku call fails for a batch, log a warning and skip that batch — the raws
are not deleted. The next consolidation run will retry.

---

## Repository Layout

```
ze/
├── memory/
│   ├── consolidator.py        # MemoryConsolidator + ConsolidationReport
│   ├── store.py               # existing — no changes needed
│   └── types.py               # existing — ConsolidationReport added here
├── api/
│   └── routes/
│       └── memory.py          # existing — add POST /memory/consolidate + digest extension
└── workflow/
    └── scheduler.py           # existing — add schedule_job() for consolidation cron
```

---

## Data Structures

`ze/memory/types.py` additions:

```python
@dataclass
class ConsolidationReport:
    facts_merged: int          # pairs resolved (either silently or via LLM)
    facts_soft_expired: int    # unreviewed facts scheduled for deletion
    facts_hard_deleted: int    # contradicted/grace-elapsed facts deleted
    episodes_archived: int     # archive batches created
    episodes_deleted: int      # raw episode rows deleted
    duration_ms: int
```

`Episode` dataclass gains two new fields (populated from DB columns):

```python
@dataclass
class Episode:
    ...
    is_archive: bool = False   # True for rolled-up archive rows
```

The `archived` column (raw episodes already swept into an archive) is only in the DB;
the Python type does not need it because archived raws are hard-deleted immediately.

---

## Database Schema

Migration `migrations/versions/004_memory_consolidation.py`.

```sql
-- user_facts: soft-expiry support
ALTER TABLE user_facts ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS user_facts_expires_idx
    ON user_facts (expires_at) WHERE expires_at IS NOT NULL;

-- episodes: mark archive summary rows
ALTER TABLE episodes ADD COLUMN IF NOT EXISTS is_archive BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS episodes_is_archive_idx
    ON episodes (is_archive) WHERE is_archive = true;
```

No new tables. Expiry and archival are handled with columns on existing tables.

---

## Configuration

Add under `memory.consolidation` in `config/config.yaml`:

```yaml
memory:
  contradiction_threshold: 0.85    # existing key — unchanged

  consolidation:
    merge_silent_threshold: 0.95   # > this → silent merge, no LLM
    merge_llm_threshold: 0.85      # > this (and < silent) → Haiku merge
    contradicted_ttl_days: 30      # hard-delete contradicted facts after N days
    unreviewed_ttl_days: 90        # soft-expire unreviewed facts after N days
    expiry_grace_days: 7           # days between soft-expire and hard-delete
    episode_recency_days: 14       # recency buffer — never archive newer than this
    episode_archive_batch: 20      # episodes per archive batch
    episode_min_archive_batch: 10  # minimum unarchived episodes to trigger a run
    nightly_cron: "0 2 * * *"      # 2 AM UTC daily
```

`Settings` reads these via `models_config["memory"]["consolidation"]`. All values
have code-level defaults so the section is optional (supports existing deployments
without config migration).

---

## `MemoryConsolidator`

`ze/memory/consolidator.py`

```python
class MemoryConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None: ...

    async def run(self) -> ConsolidationReport:
        """Run all three tasks in sequence. Returns a report."""

    async def dedup_facts(self) -> int:
        """Merge near-duplicate facts. Returns count of pairs resolved."""

    async def expire_facts(self) -> tuple[int, int]:
        """Apply expiry rules. Returns (soft_expired, hard_deleted)."""

    async def archive_episodes(self) -> tuple[int, int]:
        """Roll old episodes into archive batches. Returns (batches_created, raws_deleted)."""
```

`run()` calls the three tasks in order: `dedup_facts` → `expire_facts` → `archive_episodes`.
Tasks are independent — ordering matters only so that dedup's `contradicted=true` writes
are immediately eligible for the expiry cleanup in the same run.

### Dedup implementation notes

- Load all non-contradicted, non-expiring facts with embeddings via a single query.
  Skip facts where `embedding IS NULL` (written before the Phase 2 migration) — they
  cannot be compared.
- Compute pairwise similarity in Python using `np.dot` (embeddings are already
  L2-normalised by `SentenceTransformer.encode(normalize_embeddings=True)`).
- Skip any pair where either fact has `reviewed = true`.
- Process pairs in descending similarity order. Once a fact is merged/marked, skip
  it in subsequent pair checks within the same run (avoid chained merges in one pass).
- Haiku merge prompt:

```
You are merging two user facts that are semantically similar.
Fact A: {fact_a.key} = {fact_a.value}
Fact B: {fact_b.key} = {fact_b.value}
Return a single merged fact in JSON: {"key": "...", "value": "..."}
Use the more informative key. Keep the value concise and factual.
```

  If the Haiku call fails or returns invalid JSON, fall back to silent merge (keep
  newest) and log a warning.

### Expiry implementation notes

- All three rules run in a single DB transaction using three sequential `EXECUTE` calls.
- Grace delete fires first so that facts soft-expired in a previous run are cleaned up
  before new soft-expiry rows are created.
- Expiry does not touch `reviewed = true` facts under any condition. The WHERE clause
  for soft-expiry explicitly includes `reviewed = false`.

### Archive implementation notes

- Release the DB connection between the candidate query and the Haiku call (same pattern
  as `MemoryStore._load_episodes`).
- Mean embedding: `np.mean(np.stack([emb for emb in batch_embeddings]), axis=0)`. The
  result is not L2-normalised; normalise it before inserting:
  `mean_emb / np.linalg.norm(mean_emb)`.
- The archive row's `agent = '__archive__'` is intentionally a sentinel value that does
  not match any real agent. `_load_episodes` does not filter by agent, so archive rows
  participate in semantic retrieval like any other episode.
- Hard-delete of raw episode rows happens inside the same transaction as the archive
  insert. If the insert fails, the transaction rolls back and the raws are safe.

---

## Scheduler Integration

`WorkflowScheduler` gains one new method:

```python
def schedule_job(
    self,
    fn: Callable[[], Awaitable[None]],
    cron: str,
    job_id: str,
) -> None:
    """Register an arbitrary async cron job on the internal scheduler."""
    self._scheduler.add_job(
        fn,
        trigger=CronTrigger.from_crontab(cron),
        id=job_id,
        replace_existing=True,
    )
```

The container calls this in the lifespan after building both `WorkflowScheduler` and
`MemoryConsolidator`:

```python
workflow_scheduler.schedule_job(
    fn=memory_consolidator.run,
    cron=settings.consolidation_nightly_cron,
    job_id="memory_consolidation",
)
```

`run()` logs its `ConsolidationReport` via structlog on completion. No Telegram push —
the user sees the effects at their next `GET /memory/digest`.

---

## REST API

### `POST /memory/consolidate`

Triggers consolidation on demand. Returns the report. Authenticated via `ZE_API_KEY`
(same as all other routes).

```python
@router.post(
    "/consolidate",
    response_model=ConsolidationReportResponse,
    summary="Trigger memory consolidation",
    description=(
        "Run dedup, expiry, and episode archival immediately. "
        "Returns a report of changes made."
    ),
)
async def run_consolidation(
    consolidator: MemoryConsolidator = Depends(get_consolidator),
) -> ConsolidationReportResponse: ...
```

`get_consolidator` dependency reads `MemoryConsolidator` off `request.app.state`.

### `GET /memory/digest` extension

Add `expiring_facts` to the response. Existing fields are unchanged.

```python
class MemoryDigestResponse(BaseModel):
    unreviewed_facts: list[...]      # existing
    contradicted_facts: list[...]    # existing
    recent_episodes: list[...]       # existing
    expiring_facts: list[UserFactResponse]  # new — facts in grace period
```

DB query addition:

```sql
SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at, expires_at
FROM user_facts
WHERE expires_at IS NOT NULL AND expires_at > NOW()
ORDER BY expires_at ASC
```

A user saves an expiring fact via the existing `POST /memory/facts/review` with
`action = "confirm"` — this sets `reviewed = true` and the expiry task will
skip it henceforth (expiry rule requires `reviewed = false`). The `expires_at`
column is cleared by the confirm handler:

```sql
UPDATE user_facts SET reviewed = true, expires_at = NULL WHERE id = $1
```

---

## Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| No facts with embeddings | Dedup skips entirely, logs info |
| Haiku merge call fails | Fall back to silent merge (keep newest); log warning |
| Haiku merge returns malformed JSON | Same fallback |
| Archive Haiku call fails | Skip that batch; do not delete raws; retry next run |
| Fewer than `episode_min_archive_batch` old episodes | Archive skips entirely |
| Consolidation run exceeds 5 minutes | APScheduler misfire policy: `coalesce=True`, `max_instances=1` — the next scheduled run proceeds normally |
| `POST /memory/consolidate` called while nightly job running | `max_instances=1` on the APScheduler job prevents concurrent runs. The API endpoint acquires no lock of its own — calling it while the scheduler job is running is safe as long as both are using the same consolidator instance (which they are). Consider a simple advisory lock via `SELECT pg_try_advisory_lock(42)` if concurrent manual + scheduled runs become a problem in practice. |

---

## Dependency Injection

`MemoryConsolidator` is constructed in `container.py` alongside `MemoryStore`:

```python
memory_consolidator = MemoryConsolidator(
    pool=pool,
    embedder=embedder,
    openrouter_client=openrouter_client,
    settings=settings,
)
app.state.memory_consolidator = memory_consolidator
```

`get_consolidator` in `ze/api/dependencies.py`:

```python
def get_consolidator(request: Request) -> MemoryConsolidator:
    return request.app.state.memory_consolidator
```

---

## Testing

Tests live in `tests/memory/test_consolidator.py`.

- No real DB. Mock `asyncpg.Pool` with `AsyncMock`.
- No real OpenRouter. Mock `client.complete`.
- No real embedder. Use the `make_embedder(...)` pattern from existing memory tests.

Key scenarios:

| Test | What it verifies |
|------|-----------------|
| `test_dedup_silent_merge` | Pair above 0.95 → older fact marked contradicted, no LLM call |
| `test_dedup_llm_merge` | Pair in 0.85–0.95 → Haiku called, new merged fact inserted, both originals contradicted |
| `test_dedup_skips_reviewed` | Pair where one fact is reviewed → no merge |
| `test_dedup_llm_failure_fallback` | Haiku raises → silent merge fallback, no exception raised |
| `test_expire_grace_delete` | Facts past grace period → hard-deleted |
| `test_expire_contradicted_cleanup` | Facts with contradicted=true + old → hard-deleted |
| `test_expire_soft_expire` | Unreviewed + old → expires_at set |
| `test_expire_skips_reviewed` | reviewed=true fact → untouched regardless of age |
| `test_archive_below_minimum` | Fewer than min_archive_batch → no archival |
| `test_archive_batch` | 20 old episodes → one archive row inserted, raws deleted |
| `test_archive_haiku_failure` | Haiku raises → raws not deleted, returns (0, 0) |
| `test_run_full` | `run()` calls all three tasks, returns populated ConsolidationReport |

---

## Open Questions

All resolved.
