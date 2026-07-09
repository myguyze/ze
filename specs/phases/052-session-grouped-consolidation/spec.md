# Phase 52 — Session-Grouped Episode Consolidation

> **Package:** `ze-memory` (`ze_memory/`)
> **Phase:** 52
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `session_id` index on `memory_episodes` | ✅ Done (migration 009) |
| `current_session_id` on `RetrievalRequest` | ✅ Done |
| Current-session episode exclusion in retrieval policies | ✅ Done |
| Session-grouped archival in `MemoryConsolidator` | ✅ Done |
| Session-level summary episode | ✅ Done |
| Config knobs | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

With multi-session chat (phase 45+), each conversation has its own `thread_id` which
flows into `memory_episodes.session_id`. The existing consolidator archives the oldest
N episodes globally, mixing episodes from unrelated conversations before summarising
them. This produces vague, low-density summaries that lose the conversational thread.

Phase 52 teaches the consolidator to group episodes by session before archiving,
producing one tight summary per session that captures its entire conversational arc.
Cross-session merge then operates on these session summaries rather than raw turn-level
rows, improving signal quality for long-term memory.

---

## Responsibilities

- Group raw `memory_episodes` rows by `session_id` when archiving old episodes.
- Produce one **session summary episode** per completed session (single LLM call per session).
- Replace individual session rows with the summary archive row; delete originals.
- Fall back to the current global-batch strategy for sessions with too few episodes
  (below a minimum threshold) or for legacy `session_id` values like `app-main` and `migrated`.
- Expose session-level consolidation as a separate step in `ConsolidationReport`.

---

## Out of Scope

- Merging session summaries into a longer-term autobiography (a future phase).
- Per-agent breakdowns within a session summary.
- Rewriting or retroactively re-summarising sessions that have already been archived.
- Any change to fact consolidation (dedup/expiry) — those remain global.
- Episodes from non-chat origins (`workflow:*`, `onboarding:*`, `eval-*`) — treated as
  ungrouped and archived under the existing global-batch strategy.

---

## Module Location

```
core/ze-memory/
  ze_memory/
    consolidator.py   ← primary change: archive_episodes gains session-grouping path
    defaults.py       ← new config constants
    types.py          ← ConsolidationReport gains session_episodes_archived field
```

---

## Algorithm

### Identify sessions eligible for archival

A session is eligible when:
1. All of its episodes were created more than `episode_archive_days` ago (default 7 days).
2. The session has at least `min_session_episodes` raw episodes (default 3).
3. `session_id` is not in the excluded set: `{'migrated', 'consolidator', ''}`.
4. `session_id` does not match any non-chat prefix pattern (`workflow:`, `onboarding:`,
   `eval-`).

```sql
SELECT session_id, COUNT(*) AS n
FROM memory_episodes
WHERE created_at < now() - INTERVAL '$1 days'
  AND session_id NOT IN ('migrated', 'consolidator', '')
  AND session_id NOT LIKE 'workflow:%'
  AND session_id NOT LIKE 'onboarding:%'
  AND session_id NOT LIKE 'eval-%'
  AND summary IS NULL          -- not already archived
GROUP BY session_id
HAVING COUNT(*) >= $2          -- min_session_episodes
ORDER BY MIN(created_at)
LIMIT $3                       -- max_sessions_per_run
```

### Build the session narrative

For each eligible session, fetch its raw episodes ordered chronologically and pass them
to a single LLM call:

```
System: You are a memory consolidator. Summarise this conversation session into a
        concise third-person narrative (≤250 words). Capture: main topics, decisions,
        outcomes, and any user intent or sentiment that may be relevant in future
        sessions. Do not fabricate anything not present in the source.

User:   [turn 1 prompt]
Ze:     [turn 1 response]
[...]
```

The summary is stored as a new `memory_episodes` row with:
- `session_id = '<original_session_id>'`
- `agent = 'consolidator'`
- `prompt = '<session_id>:<n> episodes'`
- `response = <llm_summary>`
- `summary = <llm_summary>` (populated on insert, unlike raw episodes)
- `embedding = encode(summary)` (encoded from summary, not prompt)

### Delete originals

After inserting the session summary, delete all original raw rows for that session:

```sql
DELETE FROM memory_episodes
WHERE session_id = $1
  AND summary IS NULL
  AND created_at < now() - INTERVAL '$2 days'
```

### Unchanged: global-batch fallback

Sessions below `min_session_episodes`, and all excluded `session_id` values, continue
to flow through the existing `archive_episodes` batch path (global oldest-N grouping).
This preserves backward compatibility for legacy data.

---

## Data Structures

```python
# ze_memory/types.py

@dataclass
class ConsolidationReport:
    facts_merged: int = 0
    facts_soft_expired: int = 0
    facts_hard_deleted: int = 0
    episodes_archived: int = 0          # existing: global-batch archive count
    episodes_deleted: int = 0
    session_episodes_archived: int = 0  # new: sessions archived as session summaries
    profile_updated: bool = False
    duration_ms: int = 0
```

---

## Database Schema

No new tables. The `memory_episodes_session_id_idx` index added in migration 009 is the
only schema change needed to support efficient session grouping queries.

```sql
-- Already added in migration 009:
CREATE INDEX CONCURRENTLY IF NOT EXISTS memory_episodes_session_id_idx
    ON memory_episodes (session_id, created_at DESC);
```

---

## Configuration

```yaml
# config/config.yaml
memory:
  consolidation:
    # existing
    episode_archive_days: 7
    episode_archive_batch: 50

    # new in phase 52
    session_grouping_enabled: true        # master switch
    min_session_episodes: 3               # below this, use global-batch path
    max_sessions_per_run: 10             # cap LLM calls per consolidation run
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_memory.consolidator` | Extended with session-grouping archival path |
| `ze_memory.defaults` | New config constants |
| `ze_core.openrouter.client` | LLM call for session narrative summary |
| `memory_episodes_session_id_idx` | Required for efficient GROUP BY / DELETE |

---

## Implementation Notes

- **LLM cost**: One Haiku call per session × `max_sessions_per_run` = capped spend.
  At ~$0.001/call and 10 sessions/run, nightly cost is negligible.
- **Idempotency**: The `summary IS NULL` guard in both the eligibility query and the
  delete clause ensures a failed run can be safely retried without double-archiving.
- **`app-main` legacy**: Pre-sessions data with `session_id = 'app-main'` is excluded
  from session grouping (it would group thousands of turns into one call). It continues
  using the global-batch path unchanged.
- **Embedding strategy**: The summary archive row is embedded from its `summary` text,
  not the prompt column (which is just a metadata label). This matches how
  `budget_episodes` prefers `summary` over `response` for retrieval projection.
- **Current-session exclusion (already live)**: Retrieval policies already exclude the
  active `session_id` from episode results (phase 52 prerequisite, implemented
  alongside this spec). The session-grouping consolidation reinforces this: once a
  session is archived, its summary will appear in cross-session retrieval while its
  raw turns are gone, preventing double-counting against the in-thread `messages` history.

---

## Open Questions

- [ ] Should sessions from workflow/onboarding origins (`workflow:*`, `onboarding:*`) get
      their own grouping strategy, or is the global-batch fallback sufficient? Likely
      sufficient for now since those are structured flows, not open-ended conversations.
- [ ] Should the session summary be injected as a profile facet update if it reveals
      strong, stable user preferences? Probably yes — deferred to a follow-up.
- [ ] Max token limit for the session narrative prompt (currently uncapped). Should bound
      at ~8k tokens to avoid Haiku context overflows for very long sessions.
