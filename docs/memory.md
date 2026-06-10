# Ze — Memory System

Ze maintains persistent, multi-layered memory through the `ze-memory` package
(`ze_memory`). Memory is backed by Postgres + pgvector and comprises five
complementary layers. An optional graph layer adds typed relationships between
memory objects for richer context retrieval.

**Package:** `packages/ze-memory/ze_memory/`  
**Main store:** `ze_memory.retriever.PostgresMemoryStore`

---

## Data types

All types are plain dataclasses defined in `ze_memory/types.py`.

### `Fact`

Short declarative statements extracted from conversation or inferred from events.

```python
@dataclass
class Fact:
    predicate: str           # snake_case label, e.g. "communication_preference"
    value: str               # e.g. "prefers async over meetings"
    id: UUID | None = None
    subject_id: UUID | None = None   # linked Entity, if any
    object_text: str | None = None   # free-text object, if any
    object_id: UUID | None = None    # linked Entity for the object, if any
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    source_episode_id: UUID | None = None
    source_refs: list[UUID] = ...
```

**Table:** `memory_facts` — pgvector embedding on `value`.

### `Episode`

Summaries of individual conversation turns.

```python
@dataclass
class Episode:
    agent: str
    prompt: str
    response: str
    id: UUID | None = None
    session_id: str = ""
    summary: str | None = None
    relevance: float = 0.0
    created_at: datetime | None = None
    linked_entity_ids: list[UUID] = ...
    linked_fact_ids: list[UUID] = ...
```

**Table:** `memory_episodes` — pgvector embedding on `prompt + response`.

### `Event`

Discrete real-world occurrences (meetings, calls, milestones).

```python
@dataclass
class Event:
    id: UUID | None
    event_type: str       # e.g. "meeting", "call", "calendar_event"
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    participant_names: list[str] = ...   # unresolved names from extraction
    participants: list[UUID] = ...        # resolved Entity ids
    summary: str | None = None
    outcome: str | None = None
```

**Table:** `memory_events` — pgvector embedding on `title`.

When an event has an `outcome`, the store automatically extracts generalizable facts
via LLM and writes them with `PROMOTES_TO` graph edges to the extracted facts.

### `Procedure`

Reusable step-by-step instructions captured when Ze successfully executes a multi-step task.

```python
@dataclass
class Procedure:
    id: UUID | None
    name: str
    trigger: str           # When to apply this procedure
    preconditions: list[str] = ...
    steps: list[str] = ...
    success_criteria: list[str] = ...
    version: int = 1
    source_refs: list[UUID] = ...
```

**Table:** `memory_procedures` — pgvector embedding on `trigger + name`.

### `TaskState`

Live progress snapshot for a goal or workflow execution.

```python
@dataclass
class TaskState:
    id: UUID | None
    task_id: UUID | None
    goal_id: UUID | None
    status: str
    open_steps: list[str] = ...
    blocked_by: list[str] = ...
    last_action: str | None = None
    next_action: str | None = None
    tool_cursors: dict[str, str] = ...
```

**Table:** `memory_task_state`

### `ProfileFacet`

A single structured dimension of the user portrait, synthesised nightly.

```python
@dataclass
class ProfileFacet:
    key: str           # e.g. "communication_preference", "work_style"
    value: str         # e.g. "prefers async; avoids long meetings"
    stability: str     # "stable" | "dynamic"
    confidence: float = 1.0
    source_refs: list[UUID] = ...
```

**Table:** `memory_profile_facets` — upserted by key.

### `Entity`

Named entities (people, projects, tools, organisations) referenced in memory.

```python
@dataclass
class Entity:
    id: UUID | None
    entity_type: str        # e.g. "person", "project", "tool"
    canonical_name: str
    aliases: list[str] = ...
    attrs: dict[str, str] = ...
```

**Table:** `memory_entities` — pgvector embedding on `canonical_name`.

### `MemoryContext`

Assembled retrieval result injected into every agent's system prompt.

```python
@dataclass
class MemoryContext:
    facts: list[Fact] = ...
    episodes: list[Episode] = ...
    events: list[Event] = ...
    procedures: list[Procedure] = ...
    task_state: TaskState | None = None
    profile: list[ProfileFacet] = ...
    entities: list[Entity] = ...
    token_estimate: int = 0
```

---

## How memory is written

### Facts (proposed after each turn)

After each agent run, the `write_memory` graph node fires (fire-and-forget). The
`gather_fact_proposals` extractor (`ze_memory/extractor.py`) asks an LLM to extract
declarative facts from the turn. These are written via `store.propose_facts(proposals)`:

- Facts are written with `reviewed = False` and `contradicted = False`.
- Before inserting, the store checks for exact-predicate matches and semantic duplicates
  above `contradiction_threshold` — those are marked `contradicted = true`.
- The `POST /memory/facts/review` REST endpoint exposes review/edit/reject for the
  native app.

**Reviewed facts are never auto-merged or auto-expired.**

### Episodes (automatic, no approval)

After every agent run, `write_memory` calls `store.write_episode()`. The episode is
embedded and written to `memory_episodes`. The graph layer asynchronously scans the
episode text for known entity names and creates `MENTIONS` edges.

### Events

Written explicitly by agents (e.g. calendar agent writes events when syncing). Events
with `outcome` text automatically trigger LLM-based fact promotion with `PROMOTES_TO`
graph edges.

### Procedures

Written when Ze detects a reusable multi-step pattern. Linked to the goal/workflow
that produced them via `USES_PROCEDURE` graph edges.

### Task state

Upserted by `GoalExecutor` and workflow nodes to track in-flight progress. Linked to
its goal via `BELONGS_TO_GOAL` graph edges.

---

## How memory is retrieved

Before every agent execution, `fetch_context` runs:

1. **Policy lookup** — `DefaultPolicyRegistry.for_module(request.module)` returns the
   appropriate retrieval policy for the calling context.
2. **Semantic search** — pgvector cosine similarity over `memory_facts` and
   `memory_episodes` against the current prompt embedding. Token-budgeted results are
   projected via `budget_facts` and `budget_episodes`.
3. **Profile injection** — all `memory_profile_facets` rows are fetched (highest
   confidence first) and included in the context.
4. **Graph augmentation** — when `memory.graph.enabled: true` (default), entity and
   fact seed IDs from the retrieved context are expanded one hop via
   `BoundedExpansionPolicy`. Neighbour entities, facts, episodes, and procedures are
   appended to the context. Failures are silently swallowed — the base context is
   always returned.
5. **Identity block assembly** — `build_identity_block()` from `ze_personal.persona`
   assembles the system prompt identity section from the persona profile + memory
   context.

Agents never query memory themselves — they receive the assembled `MemoryContext` via
`AgentContext` and `_build_system_prompt()`.

### `RetrievalRequest`

```python
@dataclass
class RetrievalRequest:
    module: str            # e.g. "chat", "workflow", "goals"
    agent: str
    query_text: str
    query_embedding: Any   # must be set — InvalidRetrievalRequestError otherwise
    intent: str | None = None
    task_id: UUID | None = None
    goal_id: UUID | None = None
    max_tokens: int = 2000
```

---

## Graph layer

**Module:** `ze_memory.graph`  
**Config:** `memory.graph.*` in `config/config.yaml` (default: enabled)

The graph layer stores typed relationships between memory objects in the
`memory_relationships` table. Relationships have a `source_id`, `source_type`,
`predicate`, `target_id`, `target_type`, `confidence`, and `creation_method`.

### Predicates

| Predicate | Meaning |
|---|---|
| `DESCRIBES` | Entity → Fact |
| `SOURCED_FROM` | Fact → Episode |
| `MENTIONS` | Episode → Entity |
| `PARTICIPATES_IN` | Event → Entity |
| `PROMOTES_TO` | Event → Fact (from outcome extraction) |
| `BELONGS_TO_GOAL` | TaskState → Goal |
| `USES_PROCEDURE` | Procedure → Goal/Workflow |

### Traversal

`BoundedExpansionPolicy` expands from seed IDs up to `max_hops` hops (default: 1),
returning at most `max_relationships` (default: 20) neighbours. Results are merged into
the base `MemoryContext` by `enrich_context()`.

```yaml
memory:
  graph:
    enabled: true
    max_hops: 1
    max_relationships: 20
```

---

## Nightly consolidation (2 AM UTC)

**Module:** `ze_memory/consolidator.py`  
**Scheduled in:** `ze_api/container.py` via `proactive_scheduler`

`MemoryConsolidator.run()` executes four passes in sequence:

### 1. Fact deduplication

Scans all unreviewed facts, computes pairwise cosine similarity, merges candidates:

| Similarity | Action |
|---|---|
| > 0.95 | Silent merge — keep newer, mark older `contradicted = true`. No LLM call. |
| 0.85–0.95 | LLM merge — Haiku synthesises one value, inserts it, marks both originals `contradicted = true`. |
| < 0.85 | No action. |

Reviewed facts are **never** touched by consolidation.

### 2. Fact expiry

| Rule | Condition | Action |
|---|---|---|
| Grace delete | `expires_at` elapsed | Hard-delete |
| Contradicted cleanup | `contradicted = true` + older than `contradicted_ttl_days` (30d default) | Hard-delete |
| Stale unreviewed | `reviewed = false` + no activity for `unreviewed_ttl_days` (90d default) | Soft-expire: set `expires_at = NOW() + expiry_grace_days` |

### 3. Episode archival

Episodes older than `episode_recency_days` (14d default) are archived in batches.
When at least `episode_min_archive_batch` (10 default) candidates exist, Haiku
summarises the batch into one archive row and the originals are deleted.

### 4. Profile facet synthesis

After the three cleanup passes, Haiku reads all reviewed facts and recent episodes
(up to `profile.episode_limit`, default: 50) and produces a structured list of
`ProfileFacet` objects, upserted into `memory_profile_facets` by key.

Synthesis is skipped if fewer than `profile.min_facts` (3 default) reviewed facts exist.

---

## Inspecting memory

### REST API

| Endpoint | Description |
|----------|-------------|
| `GET /memory/facts` | All facts — query params: `reviewed`, `contradicted`, `expires_before` |
| `GET /memory/digest` | Unreviewed facts + facts near expiry |
| `GET /memory/profile` | Current profile facets (latest synthesis) |
| `POST /memory/facts/review` | Confirm, reject, or edit a proposed fact |
| `POST /memory/consolidate` | Trigger a consolidation run manually |

### Manual consolidation

```bash
curl -X POST https://ze-backend.fly.dev/memory/consolidate \
  -H "Authorization: Bearer $ZE_API_KEY"
```

---

## Configuration

Graph settings live in `config/config.yaml` under `memory.graph.*`.
Consolidation thresholds have code defaults in `ze_memory/defaults.py`; they can be
overridden in `config.yaml` under `memory.consolidation.*`:

```yaml
memory:
  graph:
    enabled: true
    max_hops: 1
    max_relationships: 20

  # Optional consolidation overrides (defaults defined in ze_memory/defaults.py):
  consolidation:
    merge_silent_threshold: 0.95
    merge_llm_threshold: 0.85
    contradicted_ttl_days: 30
    unreviewed_ttl_days: 90
    expiry_grace_days: 7
    episode_recency_days: 14
    episode_min_archive_batch: 10
    nightly_cron: "0 2 * * *"

  profile:
    min_facts: 3
    episode_limit: 50
```

---

## Database tables

| Table | Purpose |
|-------|---------|
| `memory_facts` | Facts with pgvector embeddings, review/contradicted status, expiry |
| `memory_episodes` | Conversation turn summaries with pgvector embeddings |
| `memory_entities` | Named entities with canonical names, aliases, pgvector embeddings |
| `memory_relationships` | Typed graph edges between memory objects |
| `memory_events` | Discrete real-world events with participants and outcomes |
| `memory_procedures` | Reusable step lists with pgvector embeddings |
| `memory_task_state` | Goal/workflow in-flight progress checkpoints |
| `memory_profile_facets` | Structured user portrait — key/value facets with confidence |

Migrations: `packages/ze-api/migrations/versions/` (raw SQL, Alembic).

---

## Key invariants

- **Reviewed facts are never auto-merged or auto-expired.** Only the user can modify them.
- **Embeddings are stored at write time only.** At query time they are dropped from context
  objects so `AgentState` stays JSON-serialisable for the LangGraph checkpointer.
- **Graph augmentation is best-effort.** Failures silently fall back to the base context
  — the store always returns something useful.
- **Memory is editorial, not automatic.** Facts require user approval opportunity;
  agents propose, users decide. Episodes are automatic because they archive away within
  ~2 weeks.
