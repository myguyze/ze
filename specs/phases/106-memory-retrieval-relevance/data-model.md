# Phase 1 Data Model: Memory Retrieval Relevance

No new database tables or migrations. Every entity below is either an existing
`ze_memory.types` dataclass gaining new **transient** (not persisted) fields, or a
new in-memory value object scoped to a single retrieval call.

## Extended entities (existing tables, new dataclass fields only)

### Fact / Episode / Entity / Event (existing dataclasses in `ze_memory/types.py`)

Each gains two new fields, never written to the database, populated per-request
by the retrieval path and dropped afterward:

| Field | Type | Meaning |
|---|---|---|
| `relevance_score` | `float \| None` | Real cosine similarity (`1 - embedding <=> query`) for vector-found candidates; `max(vector_similarity, entity_match_constant)` for entity-anchored candidates (FR-009); `None` for legacy rows with no embedding that only reached the context via the entity-anchor path. |
| `retrieval_provenance` | `Literal["vector", "entity_anchor", "graph_decoration"] \| None` | Which retrieval path found this candidate. When found by more than one path, records the path whose score won (per FR-008's "strongest evidence" rule). |

`SessionSummary` is exempted from `retrieval_provenance` (single retrieval path,
vector-only) but gains `relevance_score` for consistent floor/display treatment.

**Validation rules**:
- `relevance_score`, when not `None`, is in `[0.0, 1.0]` (pgvector cosine distance
  is bounded `[0, 2]`; the codebase already assumes normalized embeddings, so
  `1 - distance` is bounded `[-1, 1]` in theory but `[0, 1]` in practice for this
  embedding model — no new normalization needed, matches existing
  `_cosine_similarity` usage in `consolidation_store.py`).
- A candidate with `relevance_score < memory.relevance_floor` (or per-type
  override) MUST NOT appear in the `MemoryContext` returned to a policy caller
  outside `MemoryUIPolicy`/`ProfilePolicy` (FR-002).

**State transitions**: None — these are computed once per retrieval call and
discarded; no lifecycle.

## New value objects (in-memory only, no persistence)

### `RelevanceConfig` (new, `ze_memory/relevance_config.py`)

Mirrors the existing `nli_config()` resolver pattern (`ze_memory/nli_config.py`).

```python
@dataclass
class RelevanceConfig:
    floor: float                          # global default
    floor_overrides: dict[str, float]      # per memory-type override, e.g. {"episode": 0.35}
    composite_weights: CompositeWeights
    entity_anchor_enabled: bool
    entity_match_constant: float
    live_rerank_enabled: bool
    live_rerank_candidate_limit: int
    live_rerank_timeout_ms: int
```

### `CompositeWeights` (new)

```python
@dataclass
class CompositeWeights:
    similarity: float
    recency: float
    confidence: float
```

Composite score for a candidate = `similarity * w.similarity + recency_decay(age) *
w.recency + confidence * w.confidence`, computed by a new `composite_score()`
function in `ze_memory/composite.py`. Recency decay function shape (linear vs.
exponential) and exact default weights are implementation-tuning concerns per the
spec's Assumptions — not fixed here.

### `EntityAnchorMatch` (new, `ze_memory/entity_anchor.py`)

```python
@dataclass
class EntityAnchorMatch:
    entity: Entity
    matched_text: str          # the substring of the query that matched (name or alias)
    match_kind: Literal["canonical_name", "alias"]
```

Produced by `match_entities_in_query(query_text: str, pool) -> list[EntityAnchorMatch]`
— a word-bounded (see research.md item 7), case-insensitive lookup against
`memory_entities.canonical_name` and `aliases`. Canonical-name matches take
precedence over alias matches when both would match overlapping spans (per spec
Edge Cases: "prefer the canonical name over alias collisions").

### `MemoryChunkTrace` (existing, `ze_core/conversation/messages/types.py`) — extended

```python
@dataclass
class MemoryChunkTrace:
    text: str
    score: float                          # kept for backward compat — now = relevance_score
    source: str                           # "fact" | "episode" | "profile"
    extraction_confidence: float | None = None   # NEW — labelled distinctly, only for facts
```

`score` is repurposed to always mean retrieval relevance (FR-003); the previously
conflated `fact.confidence` moves to the new, explicitly-labelled
`extraction_confidence` field so the Mind panel can show both without confusion.

## Relationships (unchanged)

No new relationship predicates. Entity-anchor traversal reuses the existing
`DESCRIBES` (entity→fact), `MENTIONS` (episode→entity, signal→entity), and
`SOURCED_FROM` (fact→episode) edges already written by `PostgresMemoryStore`'s
`_link_fact_relationships` / `_link_episode_entities`. `GraphStore.expand()` is
called with the matched entity IDs as seeds instead of already-retrieved
candidate IDs — same traversal primitive, different seed source (research.md
item 8).

## Config schema addition (`apps/ze-api/config/config.yaml`, `memory:` key)

```yaml
memory:
  relevance_floor: 0.35            # global default; 0 recovers current ANN-order behaviour (FR-017)
  relevance_floor_overrides:
    episode: 0.30
  composite_weights:
    similarity: 0.6
    recency: 0.25
    confidence: 0.15
  entity_anchor:
    enabled: true
    match_constant: 0.75
  live_rerank:
    enabled: true
    candidate_limit: 20
    timeout_ms: 120
```

All values illustrative defaults — final numbers are an empirical-tuning task
against the eval suite (spec Assumptions), not fixed by this plan.
