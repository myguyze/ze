# Signal Substrate — Spec

> **Package:** `ze-memory`, `ze-news` (first emitter)
> **Phase:** 55
> **Status:** Pending
> **Depends on:** Core Memory ([../core/06-memory.md](../core/06-memory.md)), Memory Graph Augmentation ([../arch/memory-graph-augmentation.md](../arch/memory-graph-augmentation.md)), Correlation Engine ADR ([../arch/correlation-engine.md](../arch/correlation-engine.md))

---

## Implementation Status

| Feature | Status |
| ------- | ------ |
| `Signal` provenance on graph events | 🔲 Pending |
| Entity resolution for non-person entities | 🔲 Pending |
| `MemoryStore.ingest_signal()` | 🔲 Pending |
| News plugin emits signals | 🔲 Pending |
| Tests | 🔲 Pending |

---

## Purpose

External and cross-domain items (news articles today; finance, legal, email later) live
in their own tables and are invisible to the memory graph. Nothing can traverse from "the
entity Anthropic" to both a news event and a past conversation about Anthropic, because
news articles carry no `MENTIONS` edges to `memory_entities`.

This phase introduces a **signal substrate**: a uniform way for any source to promote a
salient item into the shared memory graph as a graph-anchored `Event`, with resolved
entity links. This is the only new substrate the correlation engine needs; everything
downstream is graph traversal over what already exists.

---

## Responsibilities

- Define a `Signal` — a normalized, source-agnostic representation of a salient external
  item, with provenance back to the originating store (article URL, message id, etc.).
- Anchor a signal into the memory graph as an `Event` plus `MENTIONS`/`PARTICIPATES_IN`
  edges to resolved `Entity` nodes.
- Generalize entity resolution beyond people to organizations, topics, tickers, and
  places, reusing the contacts consolidation pattern.
- Keep signals provenance-first: every signal references its source row; the engine can
  always reconstruct evidence.
- Stay bounded: admission is gated by Phase 56; this phase only defines the substrate and
  the write path.

---

## Out of Scope

- Salience scoring and the admission gate (Phase 56).
- Correlation, hypothesis formation (Phase 57), or delivery (Phase 58 inline / Phase 59 push).
- The generic plugin `SignalSource` hook (Phase 60) — this phase wires only the news
  emitter directly to prove the substrate.
- Deleting or migrating `news_articles`; the source table remains the system of record
  for its domain. Signals reference it, they do not replace it.

---

## Module Location

```
core/ze-memory/ze_memory/
    types.py            # + EntityRef, Signal dataclasses; signal_ids on GraphExpansion
    retriever.py        # ingest_signal on PostgresMemoryStore;
                        # _resolve_entity_ref helper extracted from _resolve_participant_names
    store.py            # ingest_signal on MemoryStore Protocol
    graph/
        types.py        # signal_ids: list[UUID] on GraphExpansion (already added)
        store.py        # "signal" in _TYPE_BUCKET (already added)
apps/ze-api/migrations/
    versions/NNN_memory_signals.py   # memory_signals table
plugins/ze-news/ze_news/
    signals.py          # article_to_signal(article: Article) -> Signal  (free function)
```

---

## Data Structures

`Signal` is a **new first-class graph node** (alongside `Event`, `Episode`, `Fact`).
It is not converted to an `Event` on ingest — it lives in the graph as its own type so
that retrieval policies can explicitly include or exclude external signals, and so that
`expand()` traversal stays unambiguous.

```python
# core/ze-memory/ze_memory/types.py

@dataclass
class EntityRef:
    name: str
    entity_type: str   # "person" | "org" | "topic" | "ticker" | "place" | "product"


@dataclass
class Signal:
    id: UUID
    source: str                 # plugin/source key, e.g. "news", "finance"
    external_ref: str           # stable id in the source store (article URL, ticker event id)
    title: str
    summary: str
    occurred_at: datetime
    entities: list[EntityRef] = field(default_factory=list)   # typed; resolved to Entity nodes on ingest
    magnitude: float = 0.0      # source-supplied intrinsic importance, 0..1
    payload: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None   # Phase 57 pins this when a hypothesis cites the signal
    # graph edges written on ingest: MENTIONS → Entity, PARTICIPATES_IN → Entity
```

Entities are typed at the adapter level — the adapter knows from article structure what is an org, topic, ticker, etc. This type is preserved through to `upsert_entity` so no inference is needed at resolution time.

The `external_ref` + `source` pair lets the engine reconstruct evidence from the source
table when the row still exists; the `Signal` node itself retains `title`, `summary`, and
entity edges even after the source row is pruned.

---

## Interface Contract

```python
# core/ze-memory/ze_memory/store.py  (MemoryStore protocol — additions)

class MemoryStore(Protocol):
    async def ingest_signal(self, signal: Signal) -> SignalIngestResult | None:
        """Resolve entities, write a Signal node, create MENTIONS edges.
        Returns None if the signal is a duplicate of an existing signal
        (same source + external_ref)."""
```

```python
@dataclass
class SignalIngestResult:
    signal_id: UUID
    entity_ids: list[UUID]
    created: bool          # False if deduped to an existing signal
```

### Errors / Edge Cases

| Condition | Behaviour |
| --------- | --------- |
| Duplicate `source`+`external_ref` | Return existing signal id, `created=False`; no new edges |
| Entity surface form unresolved | Create a low-confidence `Entity` (type inferred), flag for consolidation |
| Empty `entities` | Write Signal node with no entity edges; still ingestable |
| Source store row later deleted | Signal node remains; `external_ref` dangling is tolerated (evidence marked stale) |

---

## Entity Resolution

- `entity_type` extended: `person | org | topic | ticker | place | product`.
- `Topic` is a proper entity type — not a coarse tag on the signal. This enables
  cross-domain graph traversal: `Signal --MENTIONS--> Topic <--MENTIONS-- Episode`.
- Extract the core lookup-and-upsert logic from `_resolve_participant_names` into a private
  `_resolve_entity_ref(ref: EntityRef) -> UUID | None` helper on `PostgresMemoryStore`.
  `_resolve_participant_names` delegates to it with `entity_type="person"` — zero behavior
  change for the existing path. The signal ingest path calls it with the type from `EntityRef`.
- Conservative: prefer creating a new entity over a wrong merge. Consolidation (existing
  nightly job) can merge later.

---

## Graph Edges

On ingest, create:

- `Signal --MENTIONS--> Entity` for each resolved entity (including `Topic` entities).
- `Signal --PARTICIPATES_IN--> Entity` when the source marks an entity as an actor (e.g.
  the company that is the subject of a sanction), if such a distinction is available.

Predicates already exist (`ze_memory/graph/predicates.py`); no new predicate is required
for v1.

---

## News Emitter (proof of substrate)

`ze_news` gains an adapter, not new behavior in the agent:

```python
# plugins/ze-news/ze_news/signals.py

class ArticleSignalAdapter:
    def to_signal(self, article: Article) -> Signal: ...
```

The `NewsFetchJob` already returns newly-inserted `Article`s from `store.upsert()`. After
upsert, newly-inserted articles are mapped to `Signal`s. **Ingestion is still gated** by
Phase 56 — this phase wires the path but the default admission threshold may admit nothing
until Phase 56 lands. For phase 55 testing, a config flag forces ingest of all news
signals.

---

## Configuration

```yaml
# config/config.yaml
memory:
  signals:
    enabled: true
    retention_days: 90           # independent of source table pruning
    force_ingest_sources: []     # e.g. ["news"] to bypass admission in dev
```

---

## Dependencies

| Dependency | Purpose |
| ---------- | ------- |
| `ze_memory.graph` | edges + expansion |
| `ze_memory.entities` | resolution |
| `ze_sdk.errors` / `ze_agents.errors` | typed errors |

---

## Test Plan

- `ingest_signal` writes a `Signal` node and `MENTIONS` edges for resolved entities.
- Duplicate `source`+`external_ref` dedupes (returns existing signal id, `created=False`).
- `expand()` from an entity reaches both a signal and a prior episode that mention the
  same entity (the core cross-domain traversal).
- `expand()` via a shared `Topic` entity links a signal and an episode that mention the
  same topic but no common org/person.
- Non-person entities (`org`, `topic`, `ticker`) resolve and merge conservatively.
- News article → signal round-trips with `external_ref == article.url`.
- `Signal.expires_at` is `None` on ingest; remains independent of `news_articles` pruning.

---

## Open Questions

- [x] **Signal node type:** `Signal` is a new first-class graph node. Reusing `Event`
  would conflate "lived event" with "observed external event" and make retrieval policies
  unable to discriminate. See `correlation-engine.md`.
- [x] **Topic entity type:** `Topic` is a proper entity type. Coarse tags on the signal
  are insufficient — the cross-domain traversal `Signal --MENTIONS--> Topic <--MENTIONS--
  Episode` requires `Topic` to be a graph node.
- [x] **Retention:** `Signal` nodes carry their own `retention_days` (default 90),
  independent of the source table. The `Signal` node retains `title`, `summary`, and
  entity edges after source pruning. Phase 57 is responsible for pinning cited signals
  (`expires_at`) so evidence is never pruned while a hypothesis references it.
- [x] **Magnitude normalization:** Per-source z-scoring. Each source normalizes its own
  magnitude so a noisy source cannot dominate. Actual normalization is deferred until the
  second non-news source lands (finance/legal); news signals carry `magnitude=0.0` until
  then, so admission is driven entirely by relevance. Finalized in Phase 56.
