# Ze Core — Memory — Spec

## Purpose

Persist and retrieve two types of memory: stable user facts (Tier 1) and episodic
interaction history (Tier 2). Inject pre-ranked memory into agent context before
execution. Propose new facts without writing them silently — agents propose,
users confirm (or consolidation merges them automatically on a schedule).

---

## Responsibilities

- Store raw interaction episodes with pgvector embeddings.
- Retrieve relevant episodes via cosine similarity search.
- Generate and cache episode summaries lazily (on first retrieval).
- Store typed user facts (key-value, agent-scoped or global).
- Detect and mark contradictory facts (exact key match and semantic similarity).
- Inject ranked facts and episodes into `MemoryContext` within a token budget.
- Store and retrieve a structured `UserProfile` synthesised from facts and episodes.
- Run periodic consolidation: dedup facts, expire stale facts, archive old episodes,
  update the user profile.

## Out of Scope

- Does not decide what to remember — agents propose; the framework writes.
- Does not push memory digests proactively (that is a Ze-specific proactive feature).
- Does not handle cross-user memory (single-user system).
- Does not authenticate or authorise memory access.

---

## Data Types

`ze_core/memory/types.py`

```python
@dataclass
class UserFact:
    key: str
    value: str
    agent: str = "global"
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    id: UUID | None = None           # None before first DB persist
    updated_at: datetime | None = None


@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    summary: str | None = None
    relevance: float = 0.0           # populated at retrieval time; never persisted
    is_archive: bool = False
    id: UUID | None = None
    created_at: datetime | None = None
    embedding: np.ndarray | None = field(default=None, repr=False, compare=False)
    # embedding is write-time only; left None in context objects so that
    # AgentState remains JSON-serialisable for the LangGraph checkpointer.


@dataclass
class MemoryContext:
    facts: list[UserFact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    token_estimate: int = 0
    profile: UserProfile | None = None


@dataclass
class UserProfile:
    preferences: str
    habits: str
    topics: str
    relationships: str
    goals: str
    updated_at: datetime
    version: int


@dataclass
class ConsolidationReport:
    facts_merged: int = 0
    facts_soft_expired: int = 0
    facts_hard_deleted: int = 0
    episodes_archived: int = 0
    episodes_deleted: int = 0
    profile_updated: bool = False
    duration_ms: int = 0
```

### Key invariants

- `Episode.embedding` is always `None` in `MemoryContext` objects — it is only
  populated during the write path. This keeps `AgentState` JSON-serialisable for
  the LangGraph checkpointer.
- `Episode.relevance` is set at retrieval time from the pgvector cosine score.
  It is never persisted.
- `UserFact.contradicted = True` means the fact has been superseded. Contradicted
  facts are excluded from retrieval but retained for auditability.
- `UserProfile` may be `None` in `MemoryContext` if the profile row does not exist
  or all sections are empty strings.

---

## Schema

```sql
CREATE TABLE user_facts (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    agent       TEXT NOT NULL DEFAULT 'global',
    confidence  FLOAT NOT NULL DEFAULT 1.0,
    reviewed    BOOLEAN NOT NULL DEFAULT false,
    contradicted BOOLEAN NOT NULL DEFAULT false,
    embedding   VECTOR(384),        -- all-MiniLM-L6-v2, 384 dims
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE episodes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent       TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    response    TEXT NOT NULL,
    summary     TEXT,               -- NULL until first retrieval triggers generation
    embedding   VECTOR(384),
    is_archive  BOOLEAN NOT NULL DEFAULT false,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE user_profile (
    id            INT PRIMARY KEY DEFAULT 1,  -- single-row table
    preferences   TEXT NOT NULL DEFAULT '',
    habits        TEXT NOT NULL DEFAULT '',
    topics        TEXT NOT NULL DEFAULT '',
    relationships TEXT NOT NULL DEFAULT '',
    goals         TEXT NOT NULL DEFAULT '',
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    version       INT NOT NULL DEFAULT 0
);
```

pgvector extension (`CREATE EXTENSION IF NOT EXISTS vector`) must be installed.
The `embedding` column uses the `<=>` cosine distance operator.

---

## MemoryStore

`ze_core/memory/store.py`

### Constructor

```python
class MemoryStore:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
```

### `get_context()`

```python
async def get_context(
    self,
    prompt_embedding: np.ndarray,
    agent: str,
    token_budget: dict[str, int] | None = None,
) -> MemoryContext:
```

Default budget: `{"facts": 200, "episodes": 500}` (token estimates, not row counts).
Token estimate: `len(text) // 4`.

**Retrieval order for facts:**

1. Agent-scoped facts for `agent` first.
2. Among each group, ordered by semantic relevance (cosine similarity of
   `value_embedding <=> prompt_embedding`) descending, then by `updated_at` descending.
3. Only non-contradicted facts (`contradicted = false`).
4. Facts are accumulated until the token budget is exhausted.

**Retrieval order for episodes:**

1. Top-20 nearest neighbours from pgvector (`ORDER BY embedding <=> prompt_embedding LIMIT 20`).
2. Only episodes with an embedding (`embedding IS NOT NULL`).
3. Episodes are accumulated until the token budget is exhausted.
4. Missing summaries are generated concurrently via `_generate_summary()` and
   cached back to the DB before the context is returned.

**Profile:** loaded from `user_profile WHERE id = 1`. Returns `None` if the row
does not exist or all five fields are empty strings.

### `write_episode()`

```python
async def write_episode(
    self,
    agent: str,
    prompt: str,
    response: str,
    embedding: np.ndarray,
) -> None:
```

Inserts into `episodes`. Write failures are caught and logged as warnings — never
propagated. Called from `write_memory` node via `asyncio.create_task` (fire-and-forget).

### `propose_facts()`

```python
async def propose_facts(self, proposals: list[UserFact]) -> None:
```

Iterates proposals and calls `_write_fact_with_contradiction_check()` for each.
Write failures are caught and logged as warnings.

Called from `write_memory` node directly (awaited, not fire-and-forget) — fact
proposals are small and fast.

### `get_profile()`

```python
async def get_profile(self) -> UserProfile | None:
```

Returns the `user_profile` row or `None`. Called from `get_context()`.

---

## Contradiction Detection

`_write_fact_with_contradiction_check()` runs inside a single DB connection and
performs two checks before inserting the new fact:

**1. Exact key match:**
If any existing non-contradicted fact has the same `key`, mark it as contradicted
(`UPDATE user_facts SET contradicted = true WHERE id = $1`).

**2. Semantic similarity:**
Encode the new fact's `value`. For every non-contradicted fact with a different key,
encode its `value` and compute cosine similarity. If `similarity > contradiction_threshold`,
mark that fact as contradicted.

`contradiction_threshold` is read from `settings.config["memory"]["contradiction_threshold"]`.
Default: `0.85`.

The new fact is then inserted with its value embedding.

**Cost note:** The embedding-based check encodes every existing fact's value in Python.
This is acceptable for small memory stores (< 1000 facts). Applications with large
fact stores should migrate to pgvector-based nearest-neighbour search for this step.

---

## Episode Summarisation

Summaries are generated lazily — only when an episode is retrieved and its `summary`
is `NULL`.

```python
async def _generate_summary(
    self,
    episode_id: UUID,
    prompt: str,
    response: str,
) -> str | None:
```

- Model: `settings.config["models"]["synthesis"]` (default: `"anthropic/claude-haiku-4-5"`).
- Max tokens: 100.
- On success: `UPDATE episodes SET summary = $1 WHERE id = $2`.
- On failure: logs a warning; episode is served without summary (uses first 200
  chars of response as fallback for the token budget calculation).

Multiple missing summaries within a single `get_context()` call are generated
concurrently via `asyncio.gather`. DB writes are batched into a single connection
after all LLM calls complete.

---

## MemoryConsolidator

`ze_core/memory/consolidator.py`

Runs on a schedule (default: nightly at 02:00). Not called from the graph.

### Constructor

```python
class MemoryConsolidator:
    def __init__(
        self,
        pool: asyncpg.Pool,
        embedder: SentenceTransformer,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
```

### `run()`

```python
async def run(self) -> ConsolidationReport:
```

Calls each phase in order:

1. `dedup_facts()` — merge duplicate facts.
2. `expire_facts()` — soft-expire and hard-delete stale facts.
3. `archive_episodes()` — archive old episodes, delete very old ones.
4. `update_profile()` — synthesise a new `UserProfile` from remaining facts and
   episode summaries.

Returns a `ConsolidationReport` with counts for each phase.

### Fact dedup — `dedup_facts()`

For every pair of non-contradicted facts with cosine similarity above a threshold:

| Similarity range | Action |
|---|---|
| `>= merge_silent_threshold` (default: 0.95) | Merge silently — keep higher-confidence fact, mark other contradicted |
| `>= merge_llm_threshold` (default: 0.85) and `< 0.95` | Ask a small LLM to merge into a single fact; replace both |

After merging, re-embed the merged fact's value and update `embedding` in the DB.

### Fact expiry — `expire_facts()`

**Soft expiry** (mark contradicted): unreviewed facts older than
`unreviewed_ttl_days` (default: 90 days).

**Hard deletion**: contradicted facts older than `contradicted_ttl_days`
(default: 30 days since being marked contradicted).

Both TTLs are read from `settings.config["memory"]`.

### Episode archival — `archive_episodes()`

Episodes older than `episode_recency_days` (default: 14 days) that have not yet
been archived are candidates. If at least `episode_min_archive_batch` (default: 10)
candidates exist, an LLM summarises the batch into a single archival record
(`is_archive = true`), and the originals are deleted.

Raw episodes older than the archive window and without a pending archive are
hard-deleted.

### Profile update — `update_profile()`

Calls a small LLM with all non-contradicted facts and recent episode summaries.
Expects a JSON response with exactly five keys: `preferences`, `habits`, `topics`,
`relationships`, `goals`. Writes or upserts the `user_profile` row (always `id = 1`).

---

## Token Budget

The token budget controls how much memory is injected into each agent context.
Tokens are estimated as `len(text) // 4` (characters-to-tokens approximation).

| Budget key | Default | Covers |
|---|---|---|
| `facts` | 200 | Sum of `fact.value` lengths |
| `episodes` | 500 | Sum of `episode.summary or response[:200]` lengths |

Applications can override per-call by passing `token_budget` to `get_context()`.
Budget enforcement is done by accumulating facts/episodes in ranked order until the
budget is exhausted — it is not a hard DB-level limit.

---

## Integration with the Orchestration Graph

Memory is integrated at two graph nodes:

| Node | Memory call | Fire-and-forget |
|---|---|---|
| `fetch_context` | `store.get_context(prompt_embedding, agent)` | No — awaited inline |
| `write_memory` | `store.write_episode(...)` | Yes — `asyncio.create_task` |
| `write_memory` | `store.propose_facts(result.memory_proposals)` | No — awaited inline |

`write_memory` skips all memory writes when `thread_id` starts with `"eval-"`.

---

## Settings Keys

All memory settings live under `config["memory"]` in `settings.config`:

| Key | Default | Purpose |
|---|---|---|
| `contradiction_threshold` | `0.85` | Cosine similarity above which a fact is flagged as contradicted |
| `merge_silent_threshold` | `0.95` | Auto-merge without LLM |
| `merge_llm_threshold` | `0.85` | LLM-assisted merge |
| `contradicted_ttl_days` | `30` | Days before a contradicted fact is hard-deleted |
| `unreviewed_ttl_days` | `90` | Days before an unreviewed fact is soft-expired |
| `episode_recency_days` | `14` | Days before an episode is an archival candidate |
| `episode_archive_batch` | `20` | Max episodes per archival LLM call |
| `episode_min_archive_batch` | `10` | Minimum candidates before archival runs |

---

## Dependencies

| Dependency | Purpose |
|---|---|
| `asyncpg` | DB pool — all reads and writes |
| `sentence_transformers` | Encoding fact values and prompts for semantic retrieval |
| `ze_core.openrouter.client` | `OpenRouterClient` — episode summarisation, fact merging, profile synthesis |
| `ze_core.memory.types` | `UserFact`, `Episode`, `MemoryContext`, `UserProfile`, `ConsolidationReport` |
| `ze_core.errors` | `MemoryError` base class |
| `ze_core.logging` | Structured logging |

---

## Errors / Edge Cases

| Condition | Behaviour |
|---|---|
| Empty memory store | Return empty `MemoryContext`, do not error |
| Token budget exhausted mid-list | Truncate — remaining facts/episodes are omitted |
| Episode has no embedding | Excluded from semantic retrieval |
| Summary generation fails | Log warning; use `response[:200]` as fallback for budget calc |
| Fact write fails | Log warning; `propose_facts()` continues to next proposal |
| Episode write fails | Log warning; fire-and-forget task swallows the error |
| `user_profile` row absent | `get_profile()` returns `None`; `MemoryContext.profile = None` |
| All profile sections empty | Treated same as absent — returns `None` |
| Consolidation LLM call fails | Log warning; that phase returns 0 count; run continues |
| pgvector extension missing | `write_episode()` / `propose_facts()` raise at first insert — surface at startup |
