# Ze — Memory Graph Augmentation

> **Package:** `ze_memory`
> **Phase:** N/A
> **Status:** Done

---

## Context

The memory package extraction decision establishes `ze_memory` as the canonical home
for memory semantics. This follow-up decision narrows the graph question: which
relationships are worth modeling explicitly, how they interact with vector retrieval,
and what query shapes justify graph traversal at all.

This is not a decision to make memory “graph-first”. It is a decision to add explicit
relationships where they improve retrieval, provenance, and module-specific reasoning
without turning memory into an open-ended ontology or a graph-reasoning research
project.

---

## Goals

1. Model only relationships that have a concrete retrieval or audit use.
2. Keep graph augmentation subordinate to explicit state and vector retrieval.
3. Preserve provenance and confidence on every durable relationship.
4. Support module-specific retrieval queries that benefit from joins, not universal
   graph traversal.
5. Keep the implementation simple enough that it can be reasoned about and debugged
   with deterministic state plus approximate recall.

---

## In scope

### 1. First-class relationship types

The graph layer must support a small, explicit set of relationship types:

| Relation | Connects | Purpose |
|---|---|---|
| `entity -> fact` | entities to declarative facts | Attach facts to the thing they describe |
| `fact -> episode` | facts to source episodes | Provenance and auditability |
| `episode -> entity` | episodes to mentioned entities | Recall and entity-centric retrieval |
| `event -> entity` | events to participants / targets | Scheduling and decision context |
| `procedure -> task_state` | procedures to current or recent task execution | Reuse playbooks and execution state |
| `task_state -> goal` | task state to goals | Keep active work anchored to intent |
| `event -> fact` | decisions or outcomes to declarative memory | Promote durable learnings from lived events |

The exact predicate names may differ, but the relationship semantics above are part of
the contract.

### 2. Relationship creation rules

Relationships are created only when there is a clear source of truth:

- facts link to episodes when the episode is the source of the fact
- entities link to facts when the fact is about that entity
- episodes link to entities when entity extraction is sufficiently confident
- events link to entities when the participants or targets are explicit
- procedures link to task state when a task is using or reusing a procedure
- task state links to goals when the task is part of goal execution

Relationships may be inferred from extraction, but durable storage must carry the
originating source reference and confidence.

### 3. Graph retrieval augmentation

Graph traversal is allowed only after an initial candidate set has been produced by
explicit lookup or vector search.

The default pattern is:

1. retrieve candidates by module policy
2. rank by semantic relevance, recency, confidence, and review state
3. expand locally along a bounded set of explicit relations
4. re-rank the expanded set
5. project the result into `MemoryContext`

Graph traversal is an augmentation step, not a replacement for retrieval.

### 4. Query-driven module usage

Graph augmentation is justified only for a few concrete query families:

- entity-centric recall: “what do I know about this person / project / place?”
- decision tracing: “why did I decide this?” or “what led to this outcome?”
- task continuity: “what is the current state of this work?”
- procedure reuse: “how do I usually do this kind of task?”
- goal anchoring: “what work belongs to this goal?”

If a query does not benefit from one of those patterns, the retrieval policy should
prefer vector recall and deterministic state instead.

### 5. Explicit edge provenance

Every durable relationship must retain:

- source object ID
- creation method: explicit, extracted, or synthesized
- confidence
- created_at / updated_at timestamps
- optional review state when the relationship is a user-facing declarative claim

This is required so the graph can be debugged and so relationship quality can be
audited independently of node content.

---

## Out of scope

- Does not introduce hypergraphs or line graphs in the initial implementation.
- Does not define a universal ontology for all possible assistant knowledge.
- Does not make graph traversal the primary retrieval mechanism.
- Does not require learned edge embeddings for the first cut.
- Does not change the package boundary decision: this remains inside `ze_memory`.
- Does not make every relationship user-reviewable; only declarative claims follow the
  same review semantics as facts.

---

## Module Location

```
packages/ze-memory/
  ze_memory/
    graph/
      __init__.py
      types.py
      store.py
      traversal.py
      projection.py
      predicates.py
```

The graph layer is a submodule of `ze_memory`, not a separate package. It owns graph
relationships and bounded traversal logic, but it remains subordinate to the memory
store and retrieval policies.

---

## Interface Contract

The graph layer should expose explicit primitives for relationship storage and bounded
expansion.

### Input

```python
@dataclass
class Relationship:
    id: UUID | None
    source_id: UUID
    source_type: str
    predicate: str
    target_id: UUID | None = None
    target_type: str | None = None
    target_text: str | None = None
    confidence: float = 1.0
    provenance_id: UUID | None = None
    creation_method: str = "explicit"   # explicit | extracted | synthesized
    reviewed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GraphStore(Protocol):
    async def upsert_relationship(self, relationship: Relationship) -> None: ...
    async def list_relationships(self, source_id: UUID) -> list[Relationship]: ...
    async def expand(self, seed_ids: list[UUID], max_hops: int, limit: int) -> list[Relationship]: ...


class GraphTraversalPolicy(Protocol):
    async def expand(self, request: RetrievalRequest, seed_ids: list[UUID]) -> list[Relationship]: ...
```

### Output

```python
@dataclass
class GraphExpansion:
    relationships: list[Relationship] = field(default_factory=list)
    entity_ids: list[UUID] = field(default_factory=list)
    fact_ids: list[UUID] = field(default_factory=list)
    event_ids: list[UUID] = field(default_factory=list)
    procedure_ids: list[UUID] = field(default_factory=list)
```

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Seed IDs are empty | Return an empty expansion |
| Graph expansion exceeds the policy budget | Truncate deterministically |
| Relationship provenance is missing | Reject write or mark as non-durable, depending on the creation path |
| Relationship target is textual only | Allow for extracted claims, but do not treat as a canonical entity link |
| Graph and vector rankings disagree | Graph may enrich but must not override explicit task state |

---

## Data Structures

```python
@dataclass
class Relationship:
    id: UUID | None
    source_id: UUID
    source_type: str
    predicate: str
    target_id: UUID | None = None
    target_type: str | None = None
    target_text: str | None = None
    confidence: float = 1.0
    provenance_id: UUID | None = None
    creation_method: str = "explicit"
    reviewed: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class GraphExpansion:
    relationships: list[Relationship] = field(default_factory=list)
    entity_ids: list[UUID] = field(default_factory=list)
    fact_ids: list[UUID] = field(default_factory=list)
    event_ids: list[UUID] = field(default_factory=list)
    procedure_ids: list[UUID] = field(default_factory=list)
```

### Key invariants

- A relationship is only durable if it has provenance.
- Entity and fact links are the primary graph surface; everything else is secondary.
- Graph expansion must be bounded by policy, not open-ended traversal depth.
- Explicit task state always outranks graph-derived inference when the two disagree.
- Relationship predicates are controlled vocabulary, not freeform natural language.

---

## Database Schema

```sql
CREATE TABLE memory_relationships (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        UUID NOT NULL,
    source_type      TEXT NOT NULL,
    predicate        TEXT NOT NULL,
    target_id        UUID NULL,
    target_type      TEXT NULL,
    target_text      TEXT NULL,
    confidence       FLOAT NOT NULL DEFAULT 1.0,
    provenance_id    UUID NULL,
    creation_method  TEXT NOT NULL DEFAULT 'explicit',
    reviewed         BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX memory_relationships_source_idx ON memory_relationships (source_id);
CREATE INDEX memory_relationships_target_idx ON memory_relationships (target_id);
CREATE INDEX memory_relationships_predicate_idx ON memory_relationships (predicate);
```

This schema is intentionally minimal. It supports adjacency, provenance, and bounded
expansion without committing the implementation to a full graph database abstraction.

---

## Configuration

```yaml
# config/config.yaml
memory:
  graph:
    enabled: true
    max_hops: 2
    max_relationships: 20
    predicates:
      - describes
      - sourced_from
      - mentions
      - participates_in
      - uses_procedure
      - belongs_to_goal
```

The exact predicate vocabulary can evolve, but the graph layer must keep it explicit
and versionable.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_memory.types` | Base memory objects and projections |
| `ze_memory.store` | Durable storage and retrieval entry point |
| `ze_core.errors` | Typed error hierarchy |
| `ze_core.logging` | Structured logging |
| `pgvector` | Optional semantic indexing on graph-adjacent text where useful |

---

## Implementation Notes

- This spec intentionally keeps graph augmentation subordinate to retrieval policy.
- Graph augmentation should be used to enrich candidate sets, not to replace semantic
  search or explicit state lookups.
- The first implementation should prefer simple typed relationships and bounded
  expansion over clever inference.
- Relationship predicates should be selected from a controlled vocabulary to prevent
  ontology drift.
- If a query pattern does not justify graph traversal, the policy should decline to
  expand.
