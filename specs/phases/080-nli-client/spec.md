# Phase 80 — NLI Client + Plugin Access

**Status:** Done
**Depends on:** Phase 79 (NLI cross-encoder integration)
**Packages touched:** `core/ze-agents`, `core/ze-core`, `core/ze-memory`, `core/ze-correlation`, `packages/ze-sdk`, `apps/ze-api`

---

## What this is

Phase 79 integrated the NLI cross-encoder into memory and correlation callsites as a
module singleton in `ze_memory/nli.py`. That kept NLI invisible to agents and plugins.

This phase promotes NLI to a first-class `NLIClient` Protocol (parallel to `LLMClient`),
with a `LocalNLIClient` implementation in `ze-core`, constructor injection via the
engine `dep_map`, and optional shared `@tool` wrappers for the agentic loop.

Plugin adoption (news dedup, finance merchant merging) is deferred to Phase 81.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Interface | `NLIClient` Protocol in `ze_agents/nli.py` | Remote LLM and local NLI are different concerns — do not extend `LLMClient` |
| Implementation | `LocalNLIClient` in `ze_core/nli.py` | Same layer as `embeddings.py` and `OpenRouterClient` |
| SDK surface | Re-export `NLIClient` from `ze_sdk` | Plugins import from `ze_sdk`, never `ze_core` |
| Memory access | Constructor-inject `NLIClient` | Avoids `ze-memory → ze-core` import cycle |
| Config | `nli_config()` stays in `ze-memory` for memory thresholds | Backward-compatible `memory.*` keys |
| Dependencies | `sentence-transformers` + `scipy` move to `ze-core` | Model lives with its implementation |

---

## NLIClient Protocol

```python
@runtime_checkable
class NLIClient(Protocol):
    async def scores(self, pairs: list[tuple[str, str]]) -> list[dict[str, float] | None]: ...
    def grounding_score(self, hypothesis, evidence_texts, scores=None) -> float: ...
    def pair_is_scorable(self, premise, hypothesis) -> bool: ...
```

`LocalNLIClient` wraps `cross-encoder/nli-deberta-v3-small` with Latin-script guard
and `run_in_executor` for async callers.

---

## DI wiring

Registered in `build_engine_stack()` and `ZeContainer` agent dep map:

```python
nli_client = LocalNLIClient()
dep_map[NLIClient] = nli_client
dep_map[LocalNLIClient] = nli_client
```

Injected into `PostgresMemoryStore`, `MemoryConsolidator`, and `CorrelationPushConsumer`.

---

## Agent / plugin access

**Constructor injection** for domain services:

```python
def __init__(self, nli_client: NLIClient, ...) -> None:
    self._nli = nli_client
```

**Agentic loop tools** (`ze_agents/nli_tools.py`):

- `nli_check_entailment(premise, hypothesis)` — per-pair scores
- `nli_grounding(hypothesis, evidence)` — mean entailment across evidence

Agents pass `nli_client` via `agentic_loop(..., deps={"nli_client": self._nli})`.

---

## Refactored callsites

| Component | Before | After |
|---|---|---|
| `MemoryConsolidator` | `from ze_memory.nli import nli_scores_async` | `await self._nli.scores(pairs)` |
| `PostgresMemoryStore` | direct import | `await self._nli.scores(pairs)` |
| `retrieval_rerank` | module-level import | `nli_client` parameter |
| `CorrelationPushConsumer` | direct import | injected `NLIClient` |

`ze_memory/nli.py` removed — implementation lives in `ze_core/nli.py`.

---

## Implementation sequence

### 80a — Infrastructure (no plugin behavior changes)

1. `NLIClient` Protocol + `LocalNLIClient` in `ze_core/nli.py`
2. Move deps to `ze-core/pyproject.toml`
3. DI registration in bootstrap + container
4. Refactor memory/correlation callsites
5. Move unit tests to `core/ze-core/tests/test_nli.py`

### 80b — Agent surface

1. Re-export `NLIClient` from `ze_sdk`
2. `ze_agents/nli_tools.py` with shared `@tool` wrappers
3. Import `ze_agents.nli_tools` at ze-api startup

---

## Non-goals (Phase 81)

- News semantic dedup / headline mismatch
- Finance merchant alias merging
- Inline correlation grounding gate
