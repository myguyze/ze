# Phase 97 — Embedding Model Upgrade (MiniLM → multilingual-E5)

> **Status:** Pending
> **Depends on:** Phase 2 (memory retrieval), Phase 1 (routing)
> **Enables:** Reliable embedding-based routing without LLM fallback for most messages
> **Packages touched:** `core/ze-core`, `core/ze-memory`, `apps/ze-api`

---

## Summary

Replace the shared embedding model (`paraphrase-multilingual-MiniLM-L12-v2`) with
`intfloat/multilingual-e5-base`. The current model produces cosine similarity scores
of 0.2–0.4 even for clear intent matches, which means the embedding router never
clears its 0.55 confidence threshold and falls back to a Haiku LLM call on 82% of
messages. E5-base, used with its required `query:`/`passage:` prefixes, produces
scores in the 0.6–0.85 range for correct matches — making the embedding router
actually work. Because the embedder is shared between routing and memory retrieval,
all stored embeddings (facts, episodes, entities) must be nulled and recomputed on
next access.

---

## Goals

- Embedding router handles ≥70% of single-agent messages without LLM fallback
- Routing cosine scores for clear matches exceed 0.60
- Memory retrieval quality is maintained or improved
- Portuguese and English both work without accuracy regression
- Model is configurable in `config.yaml` without code changes

## Non-Goals

- Separate routing and memory embedders (same model for both, keep it simple)
- Fine-tuning the model on Ze-specific data
- Changing routing thresholds (fix the model first, tune thresholds separately if needed)
- Streaming or batched background re-embedding of stored data (on-demand recompute is sufficient)

---

## Background

The `EmbeddingRouter` in `ze_core/routing/router.py` encodes all agent descriptions
at startup into a matrix, then at inference time embeds the user message and picks
the top cosine-similarity match. If `top_score < 0.55 OR score_gap < 0.10`, it sets
`is_compound=True`, which routes to the `decompose` node, which calls the Haiku LLM
fallback.

The root problem is model choice: `paraphrase-multilingual-MiniLM-L12-v2` is trained
for paraphrase detection (are these two sentences the same?), not intent classification
(which category does this sentence belong to?). With 9 competing agents all pulling
some similarity from every sentence, scores cluster in a 0.2–0.5 band regardless of
how good the match actually is.

`intfloat/multilingual-e5-base` is trained differently: it uses asymmetric
query/passage contrastive learning, meaning it's designed to match a short query
against longer descriptive passages — exactly the routing use case. The `query:`/
`passage:` prefixes are load-bearing: without them E5 degrades toward paraphrase
behaviour.

The same `get_embedder()` singleton is used by both routing and the memory layer
(facts, episodes, retrieval, consolidation, dream gates, session summaries). Switching
models invalidates all stored embeddings. A migration nulls them; memory stores
already handle null embeddings gracefully by recomputing on next write.

---

## Design

### 1. E5Embedder wrapper

Wrap `SentenceTransformer` with a thin class that enforces E5's prefix contract:

```python
# core/ze-core/ze_core/embeddings.py

_DEFAULT_MODEL = "intfloat/multilingual-e5-base"

class E5Embedder:
    """SentenceTransformer wrapper that applies E5's query/passage prefixes."""

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self._model = SentenceTransformer(model_name)

    def encode_query(self, text: str, **kwargs) -> np.ndarray:
        return self._model.encode(f"query: {text}", normalize_embeddings=True, **kwargs)

    def encode_passage(self, text: str, **kwargs) -> np.ndarray:
        return self._model.encode(f"passage: {text}", normalize_embeddings=True, **kwargs)

    def encode(self, text: str | list[str], normalize_embeddings: bool = True, **kwargs) -> np.ndarray:
        """Compat shim for memory layer callers — treats all as passages."""
        if isinstance(text, list):
            prefixed = [f"passage: {t}" for t in text]
        else:
            prefixed = f"passage: {text}"
        return self._model.encode(prefixed, normalize_embeddings=normalize_embeddings, **kwargs)

@lru_cache(maxsize=1)
def get_embedder(model_name: str = _DEFAULT_MODEL) -> E5Embedder:
    return E5Embedder(model_name)
```

The `encode()` shim means all existing memory callers (consolidator, retriever,
dream gates, session summaries) work without changes — they all encode content as
passages, which is correct.

### 2. Router changes

`EmbeddingRouter` currently calls `embedder.encode()` for both descriptions and
user messages. Switch to the asymmetric calls:

```python
# core/ze-core/ze_core/routing/router.py

# At build time (encode descriptions):
self._agent_matrix = self._embedder.encode_passage(descriptions, ...)

# At inference time (encode user message):
prompt_vec = self._embedder.encode_query(prompt, ...)
```

No other router changes needed.

### 3. Config

Add the model name to `config.yaml` so it can be swapped without code changes:

```yaml
# apps/ze-api/config/config.yaml
models:
  embedding: intfloat/multilingual-e5-base   # add this key
```

Wire it through `Settings` → `container.py` → `get_embedder(settings.embedding_model)`.

### 4. Database migration

All stored embeddings are incompatible with the new model. NULL them:

```sql
-- core/ze-core/ze_core/migrations/versions/zc021_null_embeddings_e5_migration.py
UPDATE user_facts SET embedding = NULL;
UPDATE episodes SET embedding = NULL;
```

Check `ze-memory` tables too:

```sql
UPDATE memory_facts SET embedding = NULL WHERE embedding IS NOT NULL;
UPDATE memory_episodes SET embedding = NULL WHERE embedding IS NOT NULL;
UPDATE memory_entities SET embedding = NULL WHERE embedding IS NOT NULL;
```

Memory stores recompute embeddings lazily on next write. The only cost is that
retrieval quality degrades briefly until new interactions repopulate embeddings —
acceptable since this is a single-user assistant.

---

## Interface Contract

### Public API changes

None. `get_embedder()` signature is unchanged; callers that use `.encode()` continue
to work. The new `encode_query()` / `encode_passage()` methods are internal to
routing and not part of any public protocol.

### Errors / Edge Cases

| Condition | Behaviour |
|-----------|-----------|
| Model not cached locally | `SentenceTransformer` downloads on first startup; subsequent starts use cache |
| Null embeddings in DB after migration | Memory retrieval returns empty until repopulated — graceful degradation |
| `encode()` called with list | Batch-prefixes all as `passage:` — correct for memory writes |

---

## Database Schema

No new tables. Migration only nulls existing embedding columns.

| Table | Column | Action |
|-------|--------|--------|
| `user_facts` | `embedding` | SET NULL |
| `episodes` | `embedding` | SET NULL |
| `memory_facts` | `embedding` | SET NULL |
| `memory_episodes` | `embedding` | SET NULL |
| `memory_entities` | `embedding` | SET NULL |

---

## Dependencies

| Dependency | Version | Notes |
|------------|---------|-------|
| `sentence-transformers` | already pinned | No version change needed |
| `intfloat/multilingual-e5-base` | — | ~530MB download on first startup; cached in HF cache |

No new PyPI packages. The model is downloaded from Hugging Face Hub on first use.

---

## Alternatives Considered

| Option | Why rejected |
|--------|-------------|
| `intfloat/multilingual-e5-small` | 3 MTEB points below base; worth a quick benchmark first — if score separation is sufficient, prefer this (240MB vs 530MB). Can be set via config without code change |
| `BAAI/bge-m3` | 1.1GB, multi-vector ColBERT approach adds inference complexity; overkill for 9-class routing |
| `paraphrase-multilingual-mpnet-base-v2` | Same paraphrase-detection training problem as MiniLM; scores would still cluster |
| Separate routing vs memory embedders | Adds infrastructure complexity; both tasks benefit from E5's asymmetric training |
| Lower the confidence threshold | Embedding was making wrong picks (routing workflow/research to companion); Haiku corrects these. Lowering threshold without fixing the model trades cost for accuracy |
| Make Haiku the permanent primary router | Correct fallback but adds ~$0.001/message overhead that compounds at scale; proper embedding routing is the right fix |

---

## Testing Strategy

| Layer | What to cover | Approach |
|-------|--------------|----------|
| Unit | `E5Embedder.encode_query` / `encode_passage` prefix correctness | Assert prefix in encoded text; mock `SentenceTransformer` |
| Unit | Router uses `encode_passage` for descriptions, `encode_query` for messages | Mock embedder, assert correct method called |
| Integration | Routing scores for 5 clear-intent messages exceed 0.60 | Real E5 model, real router, no DB |
| Integration | Memory retrieval still returns relevant results post-migration | Real model, seeded test facts |
| Manual | Check routing_method distribution in messages after 20 interactions | Should show ≥70% `embedding` vs current 18% |

---

## Definition of Done

- [ ] `E5Embedder` wrapper in `ze_core/embeddings.py` with `encode_query` / `encode_passage` / `encode` shim
- [ ] `EmbeddingRouter` uses `encode_passage` for descriptions, `encode_query` for user messages
- [ ] `config.yaml` has `models.embedding` key; container passes it to `get_embedder()`
- [ ] Alembic migrations `zc022` (ze-core) and `zm013` (ze-memory) resize embedding columns to 768-dim and null all stored embeddings
- [ ] Unit tests for prefix correctness and router method dispatch
- [ ] Integration test: clear-intent messages score ≥0.60
- [ ] After deploy: routing_method distribution confirms ≥70% embedding routing
- [ ] Spec status → Done; `specs/README.md` row added

---

## Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Single model for routing + memory | Yes, share `E5Embedder` | Both tasks benefit from E5; avoids loading two ~500MB models |
| `encode()` shim treats all as passages | Yes | Memory layer encodes content (passages), never queries; safe default |
| Lazy recompute of stored embeddings | Yes | Single-user system; brief retrieval degradation is acceptable over a background job |
| Model configurable via `config.yaml` | Yes | Allows easy swap between `e5-small` and `e5-base` in prod without code deploy |

---

## Open Questions

- [ ] Benchmark `multilingual-e5-small` first — if cosine scores are discriminative enough (≥0.60 for clear matches), prefer it for lower memory footprint — João — before implementation
