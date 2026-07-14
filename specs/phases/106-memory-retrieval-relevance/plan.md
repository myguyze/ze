# Implementation Plan: Memory Retrieval Relevance

**Branch**: `106-memory-retrieval-relevance` | **Date**: 2026-07-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/phases/106-memory-retrieval-relevance/spec.md`

## Summary

Retrieval today returns raw ANN nearest-neighbours with no relevance floor, shows
extraction confidence in the Mind panel as if it were retrieval relevance, and
uses the entity/relationship graph only to *decorate* results the vector search
already found (seeded from already-retrieved facts/entities, one hop, in
`PostgresMemoryStore._graph_augment`). This phase adds: a per-candidate
relevance score computed from real cosine similarity everywhere facts/episodes/
entities/events/session-summaries are queried; a configurable relevance floor;
a second retrieval entry point that matches known entities in the query text
and pulls their one-hop graph neighbourhood *before* budgeting; a composite
score (similarity × recency decay × confidence) that orders candidates before
token budgeting instead of raw ANN order; and a synchronous NLI cross-encoder
rerank of fact candidates in the live turn (today NLI reranking of facts only
happens async, cached for a session's *next* similar query, never the first).
No new database tables — the graph, entities, and NLI model all already exist;
this phase changes scoring, ranking, and query paths, not persisted schema.

## Technical Context

**Language/Version**: Python 3.11 (existing `core/ze-memory` package), TypeScript/React for the Mind panel (`apps/ze-web`)

**Primary Dependencies**: asyncpg (pgvector `<=>` cosine distance), existing `NLIClient` (`ze_agents.nli`, phase 79/80), existing `GraphStore.expand()` (phase 60/64), `paraphrase-multilingual-MiniLM-L12-v2` embedder (unchanged — model swap is phase 97)

**Storage**: PostgreSQL via existing `memory_facts`, `memory_episodes`, `memory_entities`, `memory_events`, `memory_session_summaries`, `memory_relationships` tables — no new tables, no migration. Config-only additions to `apps/ze-api/config/config.yaml` under `memory:`.

**Testing**: pytest (`make test-memory`), `asyncio_mode = auto`, mocked asyncpg pools (`AsyncMock`), mocked `NLIClient`. Existing eval suite (`eval/scenarios/`) extended with new relevance/entity-anchor scenarios per SC-001/SC-002/SC-004.

**Target Platform**: Backend service (`apps/ze-api`, uvicorn); web client (`apps/ze-web`, Vite/React) for Mind panel display only.

**Project Type**: Existing monorepo package extension — no new package. Changes land in `core/ze-memory` (retrieval core), `core/ze-core` (trace extraction), `apps/ze-web` (Mind panel), `apps/ze-api/config/config.yaml` (defaults).

**Performance Goals**: SC-005 — median added latency < 150ms/turn with rerank enabled, < 30ms with rerank disabled, versus current baseline.

**Constraints**: Single extra pgvector query per candidate type to obtain a real similarity float (already computed internally by `<=>` — just needs to be selected, not only used in `ORDER BY`). Entity-anchor matching must be word-bounded (current `_link_episode_entities` substring match via SQL `position()` is **not** word-bounded — it needs a regex/word-boundary fix or a stricter query, since it's the pattern being reused for FR-005 alias matching, and edge cases explicitly call out substring false positives as unacceptable for this feature).

**Scale/Scope**: Touches every retrieval policy in `core/ze-memory/ze_memory/policies.py` (9 orchestration-level + 2 domain-service-level + 2 introspection), `retriever.py` (`_graph_augment`, `search_session_summaries`), `projection.py` (dataclass construction), `types.py` (new fields on `Fact`/`Episode`/`Entity`/`Event`), `ze_core/orchestration/nodes/trace.py` (score source), `ze_core/conversation/messages/types.py` (`MemoryChunkTrace` label), and the Mind panel widget in `apps/ze-web`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Spec-First Development** — Spec (with 5 clarifications) exists at `specs/phases/106-memory-retrieval-relevance/spec.md`. PASS.
- **II. Single-User Model** — No per-user scoping introduced; floor/weights are global deployment config, not per-user. PASS.
- **III. Layered Package Architecture** — All changes live in `core/ze-memory` (pure infra, no domain knowledge) and `core/ze-core` (engine trace). No plugin imports `ze_core` internals; entity-anchored retrieval reuses `GraphStore`/`BoundedExpansionPolicy` already exposed to `core/ze-memory`. PASS.
- **IV. Typed, Explicit Python** — New fields added to existing `dataclasses` in `ze_memory/types.py` (no Pydantic in domain code); no new bare exceptions — reuse `ZeError` subclasses on failure paths (e.g. rerank timeout degrades, doesn't raise). PASS.
- **V. Test Discipline** — New composite-scoring, floor, and entity-anchor logic gets unit tests with `AsyncMock` pools and a mocked `NLIClient`; no real DB or LLM calls. PASS.
- **VI. Explicit Persistence** — No schema changes; nothing to migrate. N/A.
- **VII. One LLM Gateway, Local Embeddings** — Rerank reuses the existing local NLI cross-encoder (`NLIClient`), not an LLM call; embeddings stay on the current local model per the Assumptions section (phase 97 is out of scope). PASS.

No violations. Complexity Tracking section is empty.

## Project Structure

### Documentation (this feature)

```text
specs/phases/106-memory-retrieval-relevance/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (internal module contracts — no external API)
└── tasks.md             # Phase 2 output (/speckit-tasks — not created here)
```

### Source Code (repository root)

```text
core/ze-memory/ze_memory/
├── types.py              # Fact/Episode/Entity/Event: + relevance_score, retrieval_provenance
├── defaults.py           # + RELEVANCE_FLOOR_DEFAULT, COMPOSITE_WEIGHTS_DEFAULT, ENTITY_MATCH_CONSTANT, live rerank bounds
├── relevance_config.py   # NEW — config resolver, mirrors nli_config.py pattern
├── composite.py          # NEW — composite_score(candidate) -> float; recency decay + confidence blend
├── entity_anchor.py       # NEW — match_entities_in_query(text) -> list[Entity]; one-hop anchored fetch via GraphStore.expand()
├── policies.py            # Every policy: select similarity as a column, apply floor, merge entity-anchor candidates, sort by composite score before budget_*
├── projection.py          # budget_facts/budget_episodes/etc.: consume already-sorted candidates (no re-sort), carry relevance_score/provenance through *_from_row
├── retriever.py            # retrieve(): floor + composite occur inside policy.retrieve(); live NLI rerank call added (sync, uncached) gated by config
├── retrieval_rerank.py     # + live (sync) rerank entry point alongside existing async build_retrieval_cache path
├── graph/
│   ├── store.py           # unchanged — GraphStore.expand() reused as-is
│   └── projection.py      # unchanged post-hoc decoration path stays for non-anchor graph augmentation
core/ze-core/ze_core/
├── conversation/messages/types.py   # MemoryChunkTrace: + relevance_score field, extraction_confidence kept distinct
└── orchestration/nodes/trace.py     # _extract_memory_chunks: score = fact.relevance_score (not fact.confidence)
apps/ze-api/config/config.yaml        # memory: relevance_floor, composite_weights, entity_anchor, live_rerank keys
apps/ze-web/src/
├── widgets/trace-panel/ui/TraceEntry.tsx   # display relevance score distinctly from confidence; "no relevant memories" empty state
└── entities/message/...                     # regenerated SDK types picking up MemoryChunkTrace.relevance_score
eval/scenarios/                          # new scenarios for SC-001 (no-match), SC-002 (entity-anchor), SC-004 (no regression)
```

**Structure Decision**: No new package or app. This is a within-package extension of
`core/ze-memory` (the retrieval core), with small, mechanical follow-on edits to
`core/ze-core` (trace field source) and `apps/ze-web` (display label). No migration —
all new state is either transient (per-request scores) or configuration.

## Complexity Tracking

*No constitution violations — table intentionally empty.*
