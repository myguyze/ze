# Quickstart: Validating Memory Retrieval Relevance

## Prerequisites

```bash
make db-up
make migrate          # no new migrations in this phase, but keeps chain current
make dev-eval         # backend without background jobs (needed for eval runs)
```

No new environment variables. New config lives under `memory:` in
`apps/ze-api/config/config.yaml` (see data-model.md) — hot-reloadable via
`SIGHUP $(pgrep -f uvicorn)` per existing convention, no restart needed to
retune `relevance_floor` / `composite_weights` / `entity_anchor.match_constant`.

## Story 1 — Irrelevant memories stay out of context

1. Seed a memory corpus with facts unrelated to a test topic (e.g. only
   "work notes" facts, no facts about "trump workflow").
2. Send a companion-agent query about the unrelated topic over the WebSocket
   (or via `eval/run.py` with a new scenario).
3. Expect: `MemoryContext.facts` empty (or all `relevance_score` above floor
   are non-existent), `MessageTrace.memory_chunks == []`, and the Mind panel
   shows "no relevant memories" rather than blank/ambiguous.
4. Re-run with a fact genuinely about the topic seeded — expect it retrieved,
   with `relevance_score` shown in the Mind panel (not `confidence`).

Command:
```bash
python eval/run.py --tag memory-relevance-floor
```

## Story 2 — Entity-named memories found by name

1. Seed an entity (`memory_entities`) with a canonical name and an alias,
   linked via `DESCRIBES` to a fact whose embedding is *not* close to a
   deliberately dissimilar-phrasing test query.
2. Ask a question using the entity's alias, phrased so its embedding similarity
   to the fact is low.
3. Expect: the fact still appears in the delivered context, with
   `retrieval_provenance == "entity_anchor"` and
   `relevance_score >= entity_anchor.match_constant`.
4. Ask a question mentioning no known entity — expect identical behavior to
   before this phase (vector-only), no errors.

Command:
```bash
python eval/run.py --tag memory-entity-anchor
```

## Story 3 — Best memories win the token budget

1. Seed two facts: one recent + high-confidence, one older + lower-confidence,
   both with similar vector similarity to a test query, and a fact budget that
   admits only one.
2. Confirm the recent, high-confidence fact is the one delivered (composite
   ranking, not raw ANN order).
3. Inspect logs/trace for the per-candidate `similarity`/`recency`/`confidence`
   component breakdown (FR-011 inspectability requirement).

## Story 4 — Deep rerank in the live path

1. Craft a query plus a distractor fact that clears the relevance floor but is
   topically adjacent (not truly on-topic), alongside a genuinely relevant fact
   ranked slightly lower by raw similarity.
2. With `memory.live_rerank.enabled: true`, confirm the genuinely relevant fact
   ranks above the distractor in the *first* turn (no cache warm-up needed —
   this is the synchronous path, distinct from the existing async
   `build_retrieval_cache`).
3. Disable `live_rerank.enabled` (or simulate an `NLIClient` timeout/exception)
   and confirm the turn completes using floor-and-composite ordering only, no
   user-facing failure (FR-014).

## Rollback verification (FR-017)

```yaml
memory:
  relevance_floor: 0
  entity_anchor:
    enabled: false
  live_rerank:
    enabled: false
```

With this config, retrieval order and content should match the pre-phase-106
baseline exactly — run the existing eval suite (`python eval/run.py`) and
confirm no regressions (SC-004).

## Latency check (SC-005)

```bash
python eval/run.py --tag memory-relevance-floor --tag memory-entity-anchor -- --judge
```

Compare `eval/results/*.json` turn-latency fields against a baseline run with
all four features disabled; median delta should be < 150ms with rerank enabled,
< 30ms with it disabled.
