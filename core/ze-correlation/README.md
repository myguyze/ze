# ze-correlation

Correlation engine for Ze — cross-domain hypothesis formation from the memory graph, with neighbourhood expansion and signal pinning.

## Role in Ze

Ze's memory graph connects facts, episodes, contacts, news signals, and calendar events. The correlation engine traverses this graph to surface non-obvious connections — "this news article relates to your goal about Rust" — and can push high-salience hypotheses proactively.

### Key features

- `CorrelationEngine` — LLM-driven hypothesis formation from graph seeds
- Graph neighbourhood expansion with configurable hop limits and recall guarantees
- `PostgresHypothesisStore` — persists hypotheses with evidence references
- Proactive push delivery for high-salience correlations via ntfy
- Inline correlation during conversation turns (graph node in `ze-core`)

### Integration

A graph node in `ze-core` runs inline correlation during `fetch_context`. `CorrelationJob` runs on a schedule from `ze-api`. Plugins contribute signal sources via `ZePlugin.signal_sources()` — news and calendar plugins feed the engine.

## Responsibilities

| Module | What it provides |
|---|---|
| `engine.py` | `CorrelationEngine` — forms hypotheses from graph signals |
| `store.py` | `PostgresHypothesisStore` — hypothesis persistence |
| `job.py` | `CorrelationJob` — scheduled correlation runs |
| `push.py` | `CorrelationPushConsumer` — delivers correlation insights via push |
| `prompts.py` | LLM prompt templates for hypothesis generation |
| `types.py` | `Hypothesis`, `EvidenceRef` |

## Dependencies

```mermaid
graph LR
    correlation[ze-correlation] --> agents[ze-agents]
    correlation --> memory[ze-memory]
```

Third-party: `asyncpg`.

## Usage

Wired into the orchestration graph by `ze-core` (`orchestration/nodes/correlation.py`) and started as a proactive job from `ze-api`:

```python
from ze_correlation import CorrelationEngine, PostgresHypothesisStore
```

## Testing

From the repo root:

```bash
make test-correlation
```

See [docs/testing.md](../../docs/testing.md).
