# Ze — Memory Package Extraction

> **Package:** `ze_memory` (new package)
> **Phase:** N/A
> **Status:** Done (extraction + core types); write paths for Entity/Event/Procedure/TaskState are follow-on work

---

## Purpose

Ze's memory subsystem was extracted from `ze_core` into a dedicated `ze-memory` package.
The goal is for memory to be the **substrate** for all memory-related things in Ze —
not a conversational side-car, but the single store every agent reads from and every
domain service writes to. `ze_core` retains only generic infrastructure and no
memory-domain authority after the cutover.

---

## Responsibilities

- Own all memory-specific types, storage, retrieval, and consolidation logic.
- Provide module-specific retrieval policies as explicit code objects — one per Ze agent
  and one per domain-service call site.
- Maintain long-term user facts, conversation episodes, structured events, reusable
  procedures, domain entity records, and a synthesised user profile.
- Run periodic consolidation: dedup facts, expire stale ones, archive old episodes,
  update profile.
- Provide a derived `MemoryContext` projection for orchestration and prompting.

---

## Out of Scope

- Does not own routing, orchestration, agent execution, or transport.
- Does not define persona, goals, workflow, contacts, calendar, or other domain
  services — it is the store those services write into.
- Does not make embeddings the source of truth for explicit task state.
- Does not change user-facing UI behaviour as part of the package move itself.

---

## Module Location

```
packages/ze-memory/
  ze_memory/
    __init__.py
    errors.py
    types.py
    store.py        — MemoryStore / MemoryRetrievalPolicy / MemoryPolicyRegistry protocols
    retriever.py    — PostgresMemoryStore
    policies.py     — one policy class per Ze module
    consolidator.py — MemoryConsolidator
    synthesizer.py  — ProfileSynthesizer
    projection.py   — budget helpers, row → dataclass converters
    defaults.py     — thresholds and budget constants
```

---

## Interface Contract

### Input

```python
@dataclass
class RetrievalRequest:
    module: str           # Ze agent name or domain-service identifier
    agent: str
    query_text: str
    query_embedding: Any
    intent: str | None = None
    task_id: UUID | None = None   # used by WorkflowPolicy and ToolExecutorPolicy
    goal_id: UUID | None = None   # used by GoalsPolicy and PlannerPolicy
    max_tokens: int = 2000
```

```python
class MemoryStore(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> MemoryContext: ...
    async def write_episode(self, session_id, agent, prompt, response, embedding) -> None: ...
    async def propose_facts(self, facts: list[Fact]) -> None: ...
    async def upsert_task_state(self, state: TaskState) -> None: ...
    async def get_task_state(self, task_id, goal_id) -> TaskState | None: ...
    async def get_profile(self) -> list[ProfileFacet]: ...
```

### Output

```python
@dataclass
class MemoryContext:
    facts: list[Fact] = field(default_factory=list)
    episodes: list[Episode] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    task_state: TaskState | None = None
    profile: list[ProfileFacet] = field(default_factory=list)
    entities: list[Entity] = field(default_factory=list)
    token_estimate: int = 0
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| `module` or `query_embedding` missing | Fail fast with a typed memory error |
| Unknown module requested | Fall back to `CompanionPolicy`, log a warning |
| Task state does not exist | Return `None`, not a synthetic empty state |
| Consolidation cannot produce a safe merge | Preserve both records; mark lower-confidence as contradicted |
| Derived profile is empty | Return an empty list, not a fabricated one |

---

## Data Structures

```python
@dataclass
class Fact:
    predicate: str
    value: str
    id: UUID | None = None
    subject_id: UUID | None = None      # links to Entity
    object_text: str | None = None
    object_id: UUID | None = None       # links to Entity
    confidence: float = 1.0
    reviewed: bool = False
    contradicted: bool = False
    source_episode_id: UUID | None = None
    source_refs: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)


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
    linked_entity_ids: list[UUID] = field(default_factory=list)
    linked_fact_ids: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)


@dataclass
class Event:
    """A conversational occurrence — past or future.

    Events are extracted from conversation, not from Google Calendar. If the user
    says "I had a meeting with Alice last Tuesday", that creates an Event even if
    it was never on a calendar. Events that are future and actionable may also be
    written to Google Calendar, but memory_events is the canonical record of what
    Ze knows happened or is expected to happen.
    """
    id: UUID | None
    event_type: str          # e.g. "meeting", "call", "trip", "appointment"
    title: str
    start_at: datetime | None = None
    end_at: datetime | None = None
    participants: list[UUID] = field(default_factory=list)   # Entity ids
    roles: dict[str, UUID] = field(default_factory=dict)
    summary: str | None = None
    outcome: str | None = None
    source_episode_id: UUID | None = None
    embedding: Any = field(default=None, repr=False, compare=False)


@dataclass
class Procedure:
    """A reusable pattern extracted from completed workflows or goal executions.

    When the workflow agent or goal executor completes a task, the steps are
    generalised into a Procedure so Ze can reuse the pattern for similar future tasks.
    """
    id: UUID | None
    name: str
    trigger: str
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    version: int = 1
    source_refs: list[UUID] = field(default_factory=list)
    embedding: Any = field(default=None, repr=False, compare=False)


@dataclass
class TaskState:
    """Operational progress state for in-flight goals and workflow tasks.

    The goal/workflow domain tables own the plan structure (what to do). TaskState
    owns the live execution progress (what is happening right now). Written by
    GoalExecutor and WorkflowAgent; read by GoalsPolicy and WorkflowPolicy.
    """
    id: UUID | None
    task_id: UUID | None
    goal_id: UUID | None
    status: str
    open_steps: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    last_action: str | None = None
    next_action: str | None = None
    tool_cursors: dict[str, str] = field(default_factory=dict)
    updated_at: datetime | None = None


@dataclass
class Entity:
    """A person, organisation, or place Ze knows about.

    Written by the contacts consolidator when a contact is confirmed. Facts can
    reference entities via subject_id / object_id, enabling structured statements
    like "Alice prefers email" rather than flat key/value strings.
    """
    id: UUID | None
    entity_type: str          # "person", "organisation", "place"
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    attrs: dict[str, str] = field(default_factory=dict)
    embedding: Any = field(default=None, repr=False, compare=False)


@dataclass
class ProfileFacet:
    key: str
    value: str
    stability: str            # "stable" | "dynamic" | "transient"
    confidence: float = 1.0
    source_refs: list[UUID] = field(default_factory=list)
    updated_at: datetime | None = None
```

---

## Database Schema

```sql
-- Entity graph (written by contacts consolidator)
CREATE TABLE memory_entities (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type    TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    aliases        JSONB NOT NULL DEFAULT '[]'::jsonb,
    attrs          JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding      VECTOR(384),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Long-term facts (written by fact extractor after every turn)
CREATE TABLE memory_facts (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_id        UUID NULL REFERENCES memory_entities(id),
    predicate         TEXT NOT NULL,
    object_text       TEXT NULL,
    object_id         UUID NULL REFERENCES memory_entities(id),
    value             TEXT NOT NULL,
    agent_scope       TEXT NOT NULL DEFAULT 'global',
    confidence        FLOAT NOT NULL DEFAULT 1.0,
    reviewed          BOOLEAN NOT NULL DEFAULT false,
    contradicted      BOOLEAN NOT NULL DEFAULT false,
    source_episode_id UUID NULL,
    source_refs       JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding         VECTOR(384),
    expires_at        TIMESTAMPTZ NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Conversation episodes (written by write_memory node after every turn)
CREATE TABLE memory_episodes (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        TEXT NOT NULL DEFAULT '',
    agent             TEXT NOT NULL,
    prompt            TEXT NOT NULL,
    response          TEXT NOT NULL,
    summary           TEXT NULL,
    linked_entity_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    linked_fact_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
    relevance         FLOAT NOT NULL DEFAULT 0.0,
    embedding         VECTOR(384),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Conversational events — past and future occurrences mentioned in conversation
CREATE TABLE memory_events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type        TEXT NOT NULL,
    title             TEXT NOT NULL,
    start_at          TIMESTAMPTZ NULL,
    end_at            TIMESTAMPTZ NULL,
    participants      JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Entity UUIDs
    roles             JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary           TEXT NULL,
    outcome           TEXT NULL,
    source_episode_id UUID NULL,
    embedding         VECTOR(384),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reusable procedure patterns (written by workflow/goal agents on completion)
CREATE TABLE memory_procedures (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    trigger          TEXT NOT NULL,
    preconditions    JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps            JSONB NOT NULL DEFAULT '[]'::jsonb,
    success_criteria JSONB NOT NULL DEFAULT '[]'::jsonb,
    version          INT NOT NULL DEFAULT 1,
    source_refs      JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding        VECTOR(384),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Execution progress for in-flight goals and workflow tasks
CREATE TABLE memory_task_state (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id     UUID NULL,
    goal_id     UUID NULL,
    status      TEXT NOT NULL,
    open_steps  JSONB NOT NULL DEFAULT '[]'::jsonb,
    blocked_by  JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_action TEXT NULL,
    next_action TEXT NULL,
    tool_cursors JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Synthesised user profile
CREATE TABLE memory_profile_facets (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT NOT NULL UNIQUE,
    value       TEXT NOT NULL,
    stability   TEXT NOT NULL,
    confidence  FLOAT NOT NULL DEFAULT 1.0,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Retrieval Policies

Policies come in two tiers.

### Orchestration-level (dispatched by agent name via `fetch_context` node)

| Module | Policy | What is fetched |
|--------|--------|-----------------|
| `companion` | `CompanionPolicy` | facts (top-50) + recent episodes + profile facets |
| `research` | `ResearchPolicy` | facts (top-30) + episodes — no profile, research is topic-specific |
| `goals` | `GoalsPolicy` | facts + profile facets + task state for current `goal_id` |
| `workflow` | `WorkflowPolicy` | facts (minimal) + task state for current `task_id` |
| `calendar` | `CalendarPolicy` | facts (minimal) + conversation-extracted events |
| `reminders` | `RemindersPolicy` | facts (minimal) — reminder state lives in its own store |
| `email` | `EmailPolicy` | facts + recent episodes for correspondence context |
| `prospecting` | `ProspectingPolicy` | facts + recent episodes — no profile, outbound-focused |
| `profile` | `ProfilePolicy` | all profile facets + top facts — for `/memory` introspection |
| `memory_ui` | `MemoryUIPolicy` | all types at wider budgets — for full memory UI display |

### Domain-service-level (called directly by domain services, not via graph node)

| Module | Policy | Caller | What is fetched |
|--------|--------|--------|-----------------|
| `planner` | `PlannerPolicy` | `GoalPlanner` before generating a milestone plan | facts + procedures + task state |
| `tool_executor` | `ToolExecutorPolicy` | `BaseAgent.agentic_loop()` before each tool call | facts (minimal) + task state |

Unknown modules fall back to `CompanionPolicy` with a warning log.

---

## Write Paths — Current vs. Planned

| Memory type | Written today | Planned writer |
|---|---|---|
| `Fact` | fact extractor after every turn | — |
| `Episode` | `write_memory` node after every turn | — |
| `ProfileFacet` | `ProfileSynthesizer` on consolidation schedule | — |
| `Event` | nothing | event extractor (conversation-extracted occurrences) |
| `Entity` | nothing | contacts consolidator on contact confirmation |
| `Procedure` | nothing | workflow/goal agents on task completion |
| `TaskState` | nothing | `GoalExecutor` and `WorkflowAgent` during execution |

---

## Consolidation

`MemoryConsolidator` runs on a periodic schedule:

1. **Dedup facts** — embed active facts; silently mark lower-confidence duplicate when similarity ≥ 0.95; LLM-merge when 0.80 ≤ similarity < 0.95.
2. **Expire facts** — soft-expire unreviewed facts past TTL; hard-delete contradicted facts past grace period.
3. **Archive episodes** — once count exceeds batch threshold, summarise into an archive episode and delete originals.
4. **Update profile** — `ProfileSynthesizer` calls the LLM with current facts + episode summaries to produce fresh `list[ProfileFacet]`.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.errors` | Typed error hierarchy |
| `ze_core.logging` | Structured logging |
| `ze_core.embeddings` | Shared local embedding model (paraphrase-multilingual-MiniLM-L12-v2, 384-dim) |
| `ze_core.openrouter` | LLM calls for consolidation and profile synthesis |
| `asyncpg` | PostgreSQL async driver |
| `pgvector` | Semantic retrieval over embedded memory artifacts |

---

## Integration with Ze Orchestration

The `fetch_context` node in `ze_core/orchestration/nodes/context.py` builds a
`RetrievalRequest` with `module=agent_name` and calls `store.retrieve(request)`.
The resulting `MemoryContext` flows into `AgentState.memory_context` and is unpacked
into `AgentContext.memory` for use in `_format_memory()`.

Fact extraction is injected via the LangGraph configurable dict as `"fact_extractor"` —
a callable wired in `ze_core/container.py` pointing to
`ze_memory.extractor.gather_fact_proposals`. This avoids a circular dependency between
`ze_core.orchestration` and `ze_memory`.

Domain-service-level policies (`planner`, `tool_executor`) are called by passing the
store directly to the domain service at construction time, then calling
`store.retrieve(RetrievalRequest(module="planner", ...))` inside domain logic.
