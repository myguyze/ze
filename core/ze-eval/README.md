# ze-eval

Eval infrastructure for Ze — scenario runner, LLM judge, verifier, and MCP server for automated agent testing.

## Role in Ze

Ze's agent behaviour is tested against YAML scenario definitions — routing accuracy, tool selection, response quality. `ze-eval` runs these scenarios against a live backend, scores results with deterministic verifiers and optional LLM judges, and exposes an MCP server for IDE-integrated eval workflows.

### Key features

- YAML scenario loader — scenarios live in `eval/scenarios/`
- HTTP runner — fires turns against a running `ze-api` instance
- Deterministic verifiers and optional LLM-as-judge scoring
- MCP eval server for Cursor / Claude Code integration
- Regression detection via run comparison reports

### Integration

Standalone from the runtime path — no import from `ze-api` at startup. Invoked via `make eval`, `eval/run.py`, and `make eval-server`. Requires `make dev-eval` (backend without background jobs) before running.

## Responsibilities

| Module | What it provides |
|---|---|
| `runner.py` | Scenario execution against a running Ze instance |
| `scenario.py` | YAML scenario loading and parsing |
| `judge.py` | LLM-as-judge scoring |
| `verifier.py` | Deterministic assertion checks |
| `scoring.py` | Score aggregation |
| `metrics.py` | Run metrics collection |
| `report.py` | Result report generation |
| `server.py` | MCP eval server |
| `client.py` | HTTP client for Ze API during evals |
| `types.py` | Eval domain types |

## Dependencies

No Ze package dependencies. Third-party: `httpx`, `asyncpg`, `pyyaml`, `mcp`, `langchain-mcp-adapters`.

## Usage

Scenario definitions live in `eval/scenarios/`. Run evals from the repo root:

```bash
make dev-eval    # start backend without background jobs
python eval/run.py [--judge] [--tag X] [report]
python eval/server.py   # MCP server — make eval-server
```

See [docs/eval.md](../../docs/eval.md) for the full workflow.

## Testing

From the repo root:

```bash
make test-eval
```

See [docs/testing.md](../../docs/testing.md).
