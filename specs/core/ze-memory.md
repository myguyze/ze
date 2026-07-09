# ze-memory — Memory Stack

> **Package:** `core/ze-memory` — `ze_memory/`
> **Status:** Done (78b dream pass in progress)
> **Architecture:** [arch/memory-package-split.md](../arch/memory-package-split.md), [arch/memory-graph-augmentation.md](../arch/memory-graph-augmentation.md), [arch/dream-memory.md](../arch/dream-memory.md)
> **Supersedes:** [06-memory.md (stale)](06-memory.md)

---

## Purpose

The full memory stack: write, retrieve, consolidate, and evolve what Ze knows about
the user. Memory is divided into facts (structured beliefs), episodes (raw experience
records), a relationship graph, and procedures (reusable skill patterns). The dream
subsystem runs an offline consolidation loop.

---

## Responsibilities

- **Write path** — `MemoryStore.add_fact`, `add_episode`: write new facts and episodes;
  `admission.py` gates writes (NLI contradiction check, novelty filter)
- **Retrieval** — `MemoryRetriever`: semantic search over facts and episodes using the
  shared embedding singleton; `retrieval_rerank.py` re-ranks with NLI cross-encoder
- **Graph** — `MemoryGraph`: entity and relationship store; neighbourhood traversal for
  correlation context injection
- **Consolidation** — `MemoryConsolidator`: periodic dedup, expiry, episode archival,
  session-grouped summarisation
- **Dream** — `dream/`: sleep pass (NREM: compress, dedup), dream pass (REM: synthesise
  variants), morning integration (gate scoring + critic-gated promotion to live memory)
- **Surfacing** — `surfacing.py`: relevance-scored fact surfacing for context injection
  before agent calls
- **Session summaries** — `session_summary.py`: session-grouped episode summarisation
- **Retrieval cache** — `retrieval_cache.py`: caches embedding lookups for hot facts
- **NLI config** — `nli_config.py`: thresholds for contradiction detection and re-ranking
- Migrations — `zm` chain

---

## Out of Scope

- The NLI model itself — `ze-core/nli.py` (shared singleton)
- Memory write orchestration from the graph — `ze-core` `write_memory` node
- User-facing memory API routes — `ze-api`
- Domain-specific memory content (contacts, goals) — plugin packages

---

## Module Location

```
core/ze-memory/ze_memory/
  store.py              ← MemoryStore (facts, episodes)
  retriever.py          ← MemoryRetriever (semantic search)
  graph/                ← MemoryGraph, entity/relationship store
  consolidator.py       ← MemoryConsolidator
  consolidation_store.py← ConsolidationStore (dedup state)
  admission.py          ← write-time admission gates (NLI, novelty)
  synthesizer.py        ← fact synthesis (generalisation from episodes)
  surfacing.py          ← relevance-scored surfacing for context injection
  session_summary.py    ← session-grouped summarisation
  retrieval_rerank.py   ← NLI-based re-ranking
  retrieval_cache.py    ← embedding lookup cache
  extractor.py          ← entity extraction from episodes
  relevance.py          ← salience / relevance model
  projection.py         ← structured user profile projection
  policies.py           ← MemoryPolicy definitions
  dream/                ← sleep pass, dream pass, morning integration, staging buffer
  nli_config.py         ← NLI thresholds
  defaults.py           ← default policies and settings
  types.py              ← FactRecord, EpisodeRecord, MemoryEntity, MemoryRelationship
  migrations/           ← zm chain
```

---

## Key invariants

- A compressed episode (`provenance="compressed"`) is never re-compressed. This prevents
  model collapse (TiMem's documented failure mode).
- `support_count >= 3` for fact promotion requires supporters spanning ≥ 2 distinct
  `session_id`s AND ≥ 7 calendar days. Breaks self-confirming belief clusters.
- `user_asserted` episodes cap at 1 toward `support_count` regardless of quantity
  (provenance laundering guard).
- The dream staging buffer (`dream/`) is the only path to synthetic fact promotion.
  No phase writes synthetic output directly to live memory.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `LLMClient`, `DBPool`, `Settings`, error types |
| `ze-logging` | `get_logger` |

---

## Links

- [Phase 78 — Dream Memory](../phases/078-dream-memory/spec.md)
- [Phase 79 — NLI Cross-Encoder](../phases/079-nli-model/spec.md)
- [Phase 57 — Correlation Engine](../phases/057-correlation-engine/spec.md)
