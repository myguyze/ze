# Memory — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| Episode write + pgvector embedding | ✅ Done |
| Semantic episode retrieval (cosine similarity) | ✅ Done |
| Lazy episode summarisation via Haiku, cached in DB | ✅ Done |
| Contradiction detection — exact key match | ✅ Done |
| Contradiction detection — embedding similarity | ✅ Done |
| Fact retrieval by recency + agent-scoping | ✅ Done |
| Memory digest API (`GET /memory/digest`) | ✅ Done |
| Fact review API (`POST /memory/facts/review`) | ✅ Done |
| **Semantic fact retrieval (embedding on `user_facts`)** | ✅ Done |

Background consolidation (dedup, expiry, re-embedding) is **Phase 5** — not in scope here. Memory writes fire as `asyncio.create_task()` at the end of each graph run; no background worker.

## Purpose

Persist and retrieve two types of memory: stable user facts (Tier 1) and episodic
interaction history (Tier 2). Inject pre-ranked memory into agent context before
execution. Propose new facts for user approval rather than writing silently.

## Responsibilities

- Store and retrieve typed user facts (key-value, agent-scoped or global).
- Store raw interaction episodes with embeddings (prompt + response text).
- Retrieve relevant episodes via pgvector cosine similarity search.
- Detect potential contradictions before writing new facts.
- Generate episode summaries lazily via Haiku on first retrieval; cache in DB.
- Inject ranked facts and episodes into `MemoryContext` within a token budget.
- Expose a memory digest via `GET /memory/digest` (user-requested, not pushed).

## Out of Scope

- Does not decide what to remember silently — the framework extracts and proposes;
  users confirm. Agents may still supply explicit `memory_proposals` when needed.
- Does not summarise across multiple episodes (raw retrieval only).
- Does not handle cross-user memory (single-user system).
- Does not push digest notifications proactively.

## Interface Contract

### Retrieval Input

```python
prompt_embedding: np.ndarray    # from ze/embeddings.py, already normalised
agent: str                      # for agent-scoped fact prioritisation
token_budget: dict[str, int]    # e.g. {"episodes": 500, "facts": 200}
```

### Retrieval Output

```python
MemoryContext
```

### Write Input (episode)

```python
agent: str
prompt: str
response: str
embedding: np.ndarray
```

### Write Input (fact proposal)

```python
# write_memory gathers proposals via ze_core.memory.extractor.gather_fact_proposals():
#   1. LLM extraction from (prompt, response) for the completed turn
#   2. merged with any explicit AgentResult.memory_proposals (explicit wins on key clash)
proposals: list[UserFact]
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Empty memory store | Return empty `MemoryContext`, do not error |
| Token budget exceeded | Truncate by relevance score descending |
| Exact key contradiction detected | Store both, set `contradicted=True` on older entry |
| Embedding similarity contradiction (score > 0.85) | Flag both entries, surface in digest |
| Summary generation fails (Haiku error) | Log warning, return `None` for summary field |
| Episode table has < 100 rows | Use sequential scan; ivfflat index not effective |

## Data Structures

Lives in `ze/memory/types.py`.

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID
import numpy as np

@dataclass
class UserFact:
    id: UUID
    key: str
    value: str
    agent: str              # "global" or specific agent name
    confidence: float       # 0–1, agent-assigned
    reviewed: bool          # True once user has confirmed this fact
    contradicted: bool      # True if a conflicting fact exists
    updated_at: datetime

@dataclass
class Episode:
    id: UUID
    agent: str
    prompt: str
    response: str           # raw LLM response, stored at write time
    summary: str | None     # generated lazily by Haiku, cached in DB
    embedding: np.ndarray   # 384-dim, paraphrase-multilingual-MiniLM-L12-v2
    created_at: datetime
    relevance: float = field(default=0.0)  # populated at retrieval, never persisted

@dataclass
class MemoryContext:
    facts: list[UserFact]
    episodes: list[Episode]
    token_estimate: int     # rough estimate: len(text) / 4
```

## Database Schema

```sql
-- Tier 1: User facts
CREATE TABLE user_facts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key           TEXT NOT NULL,
    value         TEXT NOT NULL,
    agent         TEXT NOT NULL DEFAULT 'global',
    confidence    FLOAT NOT NULL DEFAULT 1.0,
    reviewed      BOOLEAN NOT NULL DEFAULT FALSE,
    contradicted  BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON user_facts (agent, key);

-- Tier 2: Episodic memory
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE episodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    summary     TEXT,                       -- NULL until lazily generated
    embedding   VECTOR(384),               -- paraphrase-multilingual-MiniLM-L12-v2 dimension
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX ON episodes USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);                    -- tune to SQRT(expected_row_count)
CREATE INDEX ON episodes (agent, created_at DESC);
```

## Contradiction Detection

Checked at fact proposal time, before any write:

1. **Exact key match**: if a `UserFact` with the same `key` exists, mark the
   existing entry `contradicted=True` and surface both in the digest.
2. **Embedding similarity**: encode the proposed fact's value string and compare
   against all existing facts. If any existing fact scores > 0.85 cosine similarity
   but has a different `key`, flag both as potentially contradictory.
3. No LLM call for contradiction detection — embedding similarity is sufficient
   for Phase 2. LLM-assisted judgement can be added in Phase 4 if needed.

## Episode Summary (Lazy Generation)

- At write time: store raw `prompt` + `response`. `summary` column is `NULL`.
- At retrieval time: if `summary IS NULL`, call Haiku with a summarisation prompt.
  Cache the result in the `summary` column. Subsequent retrievals use the cached
  summary.
- If Haiku call fails: log warning, return episode with `summary=None`. The
  retrieval path must handle `None` summaries gracefully (fall back to a truncated
  raw response for context injection).

## Memory Digest

Exposed via `GET /memory/digest` (see spec-07). Returns:

```python
{
    "unreviewed_facts": list[UserFact],       # reviewed=False
    "contradicted_facts": list[UserFact],     # contradicted=True
    "recent_episodes": list[Episode],         # last 10, newest first
}
```

User reviews via `POST /memory/facts/review` — confirm, reject, or edit each fact.

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze.embeddings` | Shared `SentenceTransformer` for fact embedding |
| `ze.openrouter.client` | Haiku for lazy summary generation |
| `ze.db` | asyncpg pool for all DB operations |
| `ze.errors` | `MemoryError` |
| `ze.settings` | Similarity threshold (0.85), token budget defaults |

## Implementation Notes

- `MemoryStore` is a class injected with dependencies.

```python
class MemoryStore:
    def __init__(
        self,
        db_pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ): ...

    async def get_context(
        self,
        prompt_embedding: np.ndarray,
        agent: str,
        token_budget: dict[str, int],
    ) -> MemoryContext: ...

    async def write_episode(
        self,
        agent: str,
        prompt: str,
        response: str,
        embedding: np.ndarray,
    ) -> None: ...

    async def propose_facts(self, proposals: list[UserFact]) -> None: ...

    async def get_digest(self) -> dict: ...
```

- Token estimation: `len(text) // 4`. Rough but consistent. Use this everywhere —
  do not call a tokeniser at retrieval time.
- Agent-scoped facts are retrieved first and ranked higher; global facts are
  appended after. Within each group, order by `updated_at DESC`.
- The `ivfflat` index requires `lists` to be set at create time. If the table is
  empty or has < 100 rows, pgvector falls back to a sequential scan automatically
  only if the index has not been created. Create the index in migration
  `001_initial_schema.py` with `lists = 100`. Monitor and re-create with higher
  `lists` if the table grows past 10,000 rows.
- Episode writes must not block the LangGraph node. Fire as `asyncio.create_task`.

## Semantic Fact Retrieval (Remaining Phase 2 Work)

Currently `user_facts` has no embedding column — facts are loaded by recency and
agent-scoping, ignoring the `prompt_embedding` available in `get_context`. This means
unrelated facts consume the token budget.

### Required changes

**Migration** — add embedding column and vector index to `user_facts`:

```sql
ALTER TABLE user_facts ADD COLUMN embedding VECTOR(384);
CREATE INDEX ON user_facts USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**`propose_facts`** — encode `fact.value` and store the embedding at insert time:

```python
value_embedding = self._embedder.encode(fact.value)
await conn.execute(
    "INSERT INTO user_facts (key, value, agent, confidence, embedding) VALUES ($1, $2, $3, $4, $5::vector)",
    fact.key, fact.value, fact.agent, fact.confidence, _vec(value_embedding),
)
```

Note: the embedding similarity contradiction check already calls `self._embedder.encode(fact.value)` — reuse that result instead of encoding twice.

**`_load_facts`** — accept `prompt_embedding` and rank by cosine similarity, falling
back to recency for facts without an embedding (rows written before the migration):

```python
async def _load_facts(
    self,
    agent: str,
    token_budget: int,
    prompt_embedding: np.ndarray | None = None,
) -> list[UserFact]:
```

Query when `prompt_embedding` is provided:

```sql
SELECT id, key, value, agent, confidence, reviewed, contradicted, updated_at,
       CASE
         WHEN embedding IS NOT NULL THEN 1 - (embedding <=> $3::vector)
         ELSE 0.0
       END AS relevance
FROM user_facts
WHERE contradicted = false
ORDER BY
    CASE WHEN agent = $1 THEN 0 ELSE 1 END,
    relevance DESC,
    updated_at DESC
```

**`get_context`** — pass `prompt_embedding` through to `_load_facts`.

### Behaviour after migration

- New facts are embedded on write (reusing the encoding already done for contradiction check).
- Facts written before the migration have `embedding IS NULL`; they sort last by relevance
  and fall back to recency — no data loss, no backfill required.
- The token budget and truncation logic are unchanged.

## Open Questions

All resolved.
