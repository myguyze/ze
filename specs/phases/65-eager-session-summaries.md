# Phase 65 — Eager Session Summaries

> **Package:** `ze-memory` (`ze_memory/`), `ze-api` (`ze_api/`)
> **Phase:** 65
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `memory_session_summaries` table + migration | 🔲 Pending |
| `SessionSummaryJob` proactive job | 🔲 Pending |
| Retrieval policy: prefer summaries, suppress raw turns | 🔲 Pending |
| Phase 52 interop: skip LLM call for already-summarised sessions | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

Episode storage is per-turn (one `memory_episodes` row per user message + agent
response). For the *current* session, the in-graph `messages` history gives Ze full
conversational context. For *old* sessions, semantic retrieval returns raw per-turn
fragments — unordered, lacking session narrative, and frequently retrieved out of
context.

Phase 52 fixed this for sessions older than 7 days (archival consolidation generates
one LLM summary per session). But between session close and the 7-day archival window,
Ze can only recall raw fragments.

This phase closes that gap by generating a **session summary eagerly**, shortly after
the session becomes inactive, so that cross-session recall is always narrative-quality —
not fragment-quality.

---

## Responsibilities

- Detect sessions that have closed (no new turns for ≥ `session_inactivity_minutes`).
- Generate one LLM narrative summary per closed session (single Haiku call).
- Store the summary in a dedicated `memory_session_summaries` table with an embedding.
- Suppress raw episode turns in retrieval results when a session summary exists.
- Signal to Phase 52 consolidation that the session has already been summarised, so it
  skips the LLM call and only deletes raw episode rows.

---

## Out of Scope

- Changing how raw episodes are stored or written (per-turn storage is correct; this is
  a retrieval concern).
- Merging session summaries across sessions into a long-term autobiography (future phase).
- Non-chat session origins (`workflow:*`, `onboarding:*`, `eval-*`).
- Correlation engine changes — episodes still flow into the graph for entity/fact linking
  as before.

---

## Module Location

```
core/ze-memory/
  ze_memory/
    session_summary.py    ← new: SessionSummariser (LLM call + store write)
    retriever.py          ← extend retrieve() to search session summaries
    consolidator.py       ← check for existing summary before archival LLM call

apps/ze-api/
  ze_api/
    jobs/
      session_summary_job.py  ← new: SessionSummaryJob (ProactiveJob)
  migrations/versions/
    NNN_session_summaries.py  ← new table
```

---

## Algorithm

### 1. Detecting closed sessions (SessionSummaryJob)

The job runs every `check_interval_minutes` (default 10). It queries for sessions
eligible for eager summarisation:

```sql
SELECT
    e.session_id,
    COUNT(*)                        AS episode_count,
    MAX(e.created_at)               AS last_turn_at,
    MAX(s.summary_updated_at)       AS existing_summary_at
FROM memory_episodes e
LEFT JOIN memory_session_summaries s ON s.session_id = e.session_id
WHERE
    e.summary IS NULL                      -- raw turns only
    AND e.session_id NOT IN ('migrated', 'consolidator', '')
    AND e.session_id NOT LIKE 'workflow:%'
    AND e.session_id NOT LIKE 'onboarding:%'
    AND e.session_id NOT LIKE 'eval-%'
GROUP BY e.session_id
HAVING
    COUNT(*) >= $2                         -- min_episodes (default 2)
    AND MAX(e.created_at) < now() - INTERVAL '$1 minutes'  -- session inactive
    AND (
        MAX(s.summary_updated_at) IS NULL                   -- no summary yet
        OR MAX(e.created_at) > MAX(s.summary_updated_at)    -- new turns since last summary
    )
ORDER BY MAX(e.created_at) ASC
LIMIT $3                                   -- max_sessions_per_run (default 5)
```

The inactivity threshold (`$1`) is the same `session_inactivity_minutes` used in
`fetch_context` (default 30), so Ze's session-close concept is consistent across the
codebase.

Two cases trigger summarisation:
- **No summary yet** — first time this session has closed.
- **Summary exists but stale** — the user reopened the session (same `session_id`),
  added more turns, then went inactive again. The summary must be regenerated to cover
  the new turns. A summary is considered stale when `MAX(episode.created_at) >
  summary.summary_updated_at`.

### 2. Generating the summary (SessionSummariser)

For each eligible session, fetch its raw turns ordered chronologically:

```sql
SELECT agent, prompt, response, created_at
FROM memory_episodes
WHERE session_id = $1 AND summary IS NULL
ORDER BY created_at ASC
```

Build a transcript and call the LLM:

```
System: You are a memory consolidator for a personal AI assistant. Your task is
        to write a concise third-person narrative summary (≤200 words) of the
        following conversation session.

        Capture: main topics discussed, decisions made, outcomes reached, and any
        user intent or sentiment worth remembering in future sessions. Do not add
        information that is not present in the source. Use past tense.

User:   Session: <session_id>
        <turn-1-prompt>
        Ze: <turn-1-response>
        ---
        <turn-2-prompt>
        Ze: <turn-2-response>
        [...]
```

The summary is a plain string (no JSON). If the transcript exceeds
`max_transcript_tokens` (default 6 000), drop turns from the **oldest end first**
until it fits — preserving recent turns, which capture outcomes and decisions more
faithfully than setup context.

### 3. Storing the summary

Upsert into `memory_session_summaries` — this handles both the first write and
regeneration after new turns:

```python
await store.upsert_session_summary(
    session_id=session_id,
    summary=summary_text,
    episode_count=n,
    last_turn_at=last_turn_at,
    embedding=embedder.encode(summary_text),
)
```

```sql
INSERT INTO memory_session_summaries
    (session_id, summary, episode_count, last_turn_at, summary_updated_at, embedding)
VALUES ($1, $2, $3, $4, now(), $5)
ON CONFLICT (session_id) DO UPDATE SET
    summary            = EXCLUDED.summary,
    episode_count      = EXCLUDED.episode_count,
    last_turn_at       = EXCLUDED.last_turn_at,
    summary_updated_at = now(),
    embedding          = EXCLUDED.embedding;
```

Raw episode rows are **not deleted** at this point — they remain for:
- Fact and entity extraction (already done inline at write time, but schema integrity)
- Phase 52 archival cleanup (deletes raw rows after 7 days as usual)

### 4. Retrieval changes

`MemoryStore.retrieve()` adds a second query against `memory_session_summaries`
ranked by cosine similarity to the query embedding (same budget/ranking mechanism as
episodes). Session IDs that have a summary row are excluded from the raw episode
retrieval query, so the caller never sees both raw turns and the summary for the same
session.

The episode retrieval query excludes closed sessions via a subquery rather than
fetching all summarised session IDs into Python first:

```sql
-- Retrieve raw episodes, skipping sessions that already have a summary
SELECT id, session_id, agent, prompt, response, summary, created_at, embedding
FROM memory_episodes
WHERE
    session_id != $current_session_id
    AND session_id NOT IN (SELECT session_id FROM memory_session_summaries)
    AND embedding <=> $query_embedding < $threshold
ORDER BY embedding <=> $query_embedding
LIMIT $limit;
```

The session summary retrieval is a separate ranked query against
`memory_session_summaries`, merged with the episode results and budgeted together.

Results land in separate fields — `MemoryContext.episodes` for raw turns (current
session only after the subquery exclusion), `MemoryContext.session_summaries` for
session narratives — and are rendered as distinct blocks in agent prompts.

### 5. Phase 52 interop

`MemoryConsolidator.archive_session_episodes()` checks if a summary already exists
before making an LLM call:

```python
existing = await self._store.get_session_summary(session_id)
if existing:
    # Summary already written eagerly — skip LLM, just delete raw rows
    await self._store.delete_episodes_by_session(session_id)
    continue
```

This makes phase 52 purely a cleanup step for eagerly-summarised sessions (no LLM
cost), and the LLM-generating path in phase 52 becomes the fallback for sessions that
the eager job missed (e.g., sessions that ended during a downtime window).

---

## Data Structures

```python
# ze_memory/types.py — new

@dataclass
class SessionSummary:
    id: UUID
    session_id: str
    summary: str
    episode_count: int
    last_turn_at: datetime
    created_at: datetime
    summary_updated_at: datetime
    embedding: Any = field(default=None, repr=False, compare=False)
```

```python
# ze_memory/types.py — updated

@dataclass
class MemoryContext:
    facts: list[Fact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    session_summaries: list[SessionSummary] = field(default_factory=list)  # new
    events: list[Event] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    task_state: TaskState | None = None
    profile: list[ProfileFacet] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    token_estimate: int = 0
```

Agent prompts that render `memory_context.episodes` should also render
`memory_context.session_summaries` — labelled distinctly as past session narratives.
See implementation notes.

---

## Database Schema

```sql
-- migrations/versions/NNN_session_summaries.py

CREATE TABLE memory_session_summaries (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id         TEXT        NOT NULL UNIQUE,
    summary            TEXT        NOT NULL,
    episode_count      INT         NOT NULL,
    last_turn_at       TIMESTAMPTZ NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    summary_updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    embedding          VECTOR(384)
);

-- For job eligibility query: find sessions with stale or missing summary
CREATE INDEX memory_session_summaries_updated_idx
    ON memory_session_summaries (summary_updated_at DESC);

-- For vector search: lists=10 is appropriate at personal-assistant scale
-- (tune upward when table exceeds ~1 000 rows; consider HNSW past ~10 000)
CREATE INDEX memory_session_summaries_embedding_idx
    ON memory_session_summaries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 10);
```

---

## Configuration

```yaml
# config/config.yaml
memory:
  session_summary:
    enabled: true
    check_interval_minutes: 10       # how often SessionSummaryJob runs
    min_episodes: 2                  # sessions shorter than this are skipped
    max_sessions_per_run: 5          # cap LLM calls per job execution
    max_transcript_tokens: 6000      # truncate before LLM call
    model: anthropic/claude-haiku-4-5
```

The `session_inactivity_minutes` key (already in use by `fetch_context`) is reused as
the inactivity threshold — no new key needed.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_memory.retriever` | Extended to query `memory_session_summaries` |
| `ze_memory.consolidator` | Modified to skip LLM for pre-summarised sessions |
| `ze_proactive.scheduler` | Registers `SessionSummaryJob` |
| `ze_core.openrouter.client` | LLM call for summary generation |
| `ze_memory.embeddings` | Embed summary text for vector search |
| `pgvector` | IVFFlat index on `memory_session_summaries.embedding` |

---

## Implementation Notes

- **Agent prompt rendering**: The `_build_memory_section` helpers in agent instructions
  currently only render `episodes`. Session summaries should be rendered in a separate
  `## Past Sessions` block, not merged into `## Recent Episodes`, so the LLM knows
  these are session-level narratives, not individual turns.

- **Token budget**: Session summaries share the same 2 000-token budget used in
  `RetrievalRequest.max_tokens`. The budget allocator should prefer session summaries
  over raw episodes (higher information density per token) when tokens are scarce.

- **Idempotency**: The `UNIQUE` constraint on `memory_session_summaries.session_id`
  ensures concurrent job executions can't double-write. The upsert (`ON CONFLICT DO
  UPDATE`) is safe to run multiple times — if two job instances race, the second write
  just overwrites with an identical summary.

- **Phase 52 fallback**: Sessions that closed during downtime and fell past the 7-day
  window without an eager summary will be handled by phase 52's LLM call as before.
  This is acceptable — the eager job is best-effort.

- **Very short sessions** (< `min_episodes` turns) are skipped — they're not worth an
  LLM call and their raw turns will be handled by the global-batch fallback in phase 52.

- **Cost**: At default settings — 5 sessions per run, every 10 minutes — the worst-case
  is 5 × 144 = 720 Haiku calls/day. In practice the load is much lower (most 10-minute
  windows have 0 eligible sessions). At ~$0.001 per call, daily cost is negligible.

---

## Open Questions

- [ ] Should `session_summaries` be surfaced in the `/status` introspection command so
      the user can see what Ze remembers about past sessions?
- [ ] Should very long sessions (> `max_transcript_tokens`) get a two-pass summary
      (chunk → merge) instead of truncation? Probably not for v1 — oldest-turn
      truncation preserves outcomes and decisions, which matter most for recall.
- [x] Should the eager summary be regenerated if new turns arrive after it was written
      (i.e., user reconnects within the same `session_id`)? **Yes.** The eligibility
      query checks `MAX(episode.created_at) > summary.summary_updated_at`; if true the
      session is re-summarised over its full turn history and the row is upserted.
