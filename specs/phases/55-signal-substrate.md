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
    types.py            # + Signal dataclass
    signals.py          # SignalIngestor: Signal -> Event + entity edges
    entities/
        resolver.py     # EntityResolver generalized to org/topic/ticker/place
plugins/ze-news/ze_news/
    signals.py          # ArticleSignalAdapter: Article -> Signal
```

---

## Data Structures

```python
# core/ze-memory/ze_memory/types.py

@dataclass
class Signal:
    source: str                 # plugin/source key, e.g. "news", "finance"
    external_ref: str           # stable id in the source store (article URL, ticker event id)
    title: str
    summary: str
    entities: list[str]         # surface forms; resolved to Entity nodes on ingest
    topics: list[str]           # coarse tags for relevance matching
    occurred_at: datetime
    magnitude: float = 0.0      # source-supplied intrinsic importance, 0..1
    payload: dict[str, Any] = field(default_factory=dict)
```

A `Signal` is converted to an `Event` (existing type) on ingest. No new node type is
introduced — `Event` already carries participants, summary, and outcome. The
`external_ref` + `source` pair is stored on the event provenance so evidence is always
reconstructable.

---

## Interface Contract

```python
# core/ze-memory/ze_memory/store.py  (MemoryStore protocol — additions)

class MemoryStore(Protocol):
    async def ingest_signal(self, signal: Signal) -> SignalIngestResult | None:
        """Resolve entities, write an Event, create MENTIONS edges.
        Returns None if the signal is a duplicate of an existing event
        (same source + external_ref)."""
```

```python
@dataclass
class SignalIngestResult:
    event_id: UUID
    entity_ids: list[UUID]
    created: bool          # False if deduped to an existing event
```

### Errors / Edge Cases

| Condition | Behaviour |
| --------- | --------- |
| Duplicate `source`+`external_ref` | Return existing event id, `created=False`; no new edges |
| Entity surface form unresolved | Create a low-confidence `Entity` (type inferred), flag for consolidation |
| Empty `entities` | Anchor event with topic edges only; still ingestable |
| Source store row later deleted | Event remains; `external_ref` dangling is tolerated (evidence marked stale) |

---

## Entity Resolution

Generalize the existing person-focused resolver:

- `entity_type` extended: `person | org | topic | ticker | place | product`.
- Reuse alias/embedding matching from contacts consolidation; do not build a new resolver.
- Conservative: prefer creating a new entity over a wrong merge. Consolidation (existing
  nightly job) can merge later.

---

## Graph Edges

On ingest, create:

- `Event --MENTIONS--> Entity` for each resolved entity.
- `Event --PARTICIPATES_IN--> Entity` when the source marks an entity as an actor (e.g.
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

- `ingest_signal` writes an `Event` and `MENTIONS` edges for resolved entities.
- Duplicate `source`+`external_ref` dedupes (returns existing id, `created=False`).
- `expand()` from an entity reaches both a signal-derived event and a prior episode that
  mentions the same entity (the core cross-domain traversal).
- Non-person entities (org/topic) resolve and merge conservatively.
- News article → signal → event round-trips with `external_ref == article.url`.

---

## Open Questions

- [ ] Reuse `Event` (leaning yes) or add a dedicated `Signal` node type? Reuse keeps the
  graph simple but conflates "lived event" with "observed external event" — is the
  provenance marker enough to disambiguate for retrieval policies?
- [ ] Should `magnitude` be normalized per-source (z-scored) so a finance source cannot
  dominate a news source, or globally? (Likely per-source; finalize in Phase 56.)
- [ ] Do topic edges need a `Topic` entity type, or are coarse tags on the event enough
  for relevance matching?
- [ ] Retention: signals inherit source retention (news prunes at 7 days) but the derived
  event may be referenced by a hypothesis. Should anchoring an event extend retention?
