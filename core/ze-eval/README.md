# ze-eval

Eval infrastructure for Ze — scenario runner, LLM judge, verifier, and MCP server for automated agent testing.

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
