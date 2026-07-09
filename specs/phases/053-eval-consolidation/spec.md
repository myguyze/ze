# Eval Consolidation — Spec

> **Package:** `ze-eval` (`core/ze-eval/`)
> **Phase:** 53
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `core/ze-eval/` package with `pyproject.toml` | ✅ Done |
| Top-level `eval/` directory (scenarios, `run.py`, `server.py`) | ✅ Done |
| `make dev-eval`, `make eval-server` targets | ✅ Done |
| MCP eval server | ✅ Done |

---

## Purpose

The eval framework previously lived as a flat, unpackaged Python module at `evals/`
in the repo root. Phase 53 extracted infrastructure into `core/ze-eval/` and relocated
test data and entrypoints to top-level `eval/`.

A secondary goal is to lay the groundwork for adopting
[DeepEval](https://docs.confident-ai.com/) as an evaluation metrics layer. The
current `judge.py` is a single bespoke OpenRouter call that scores quality, tone,
and tool_use in one prompt. DeepEval's `GEval` is a direct, composable replacement
that is more maintainable and leaves room for additional metrics (hallucination,
bias, toxicity) in follow-up phases. This spec does not adopt DeepEval — it
structures the package so adoption in a later phase is a contained change to
`ze_eval/judge.py` only.

---

## Responsibilities

- Define the `ze_eval` Python package as the single importable library for all eval
  infrastructure.
- Own the HTTP client for the Ze eval endpoint, the LLM judge, the database
  verifier, the session metrics fetcher, the runner orchestrator, the report
  printer, and the MCP server.
- Declare its own dependencies explicitly in `pyproject.toml` — not inherited from
  `ze-api` or the workspace root.
- Expose a clean public surface through `ze_eval/__init__.py` so the MCP server
  and CLI entrypoints stay thin.
- Hold no test data. YAML scenarios and JSON results belong in `eval/`, not in the
  package itself.

---

## Out of Scope

- Does not touch `ze_api/api/routes/eval.py` — that is the server-side eval
  endpoint and remains in `ze-api`.
- Does not adopt DeepEval metrics — that is a follow-up phase. This spec
  structures the package boundary, not the metric implementation.
- Does not add new scenarios, new tags, or new YAML fields.
- Does not change the `make eval` output format or the JSON result schema.
- Does not add CI/CD automation for eval runs — deferred.

---

## Current State

```
ze/
└── evals/
    ├── __init__.py
    ├── client.py          # ZeEvalClient — HTTP wrapper for /eval/chat
    ├── judge.py           # LLM-as-judge via OpenRouter (quality/tone/tool_use)
    ├── metrics.py         # Session token + latency metrics from llm_cost_log
    ├── verifier.py        # DB row assertions post-execution
    ├── runner.py          # Orchestration: load → run → score → print → save
    ├── report.py          # Summary printer + run diff
    ├── mcp_server.py      # MCP server (ze_chat, ze_list_scenarios, ze_run_scenario, ze_run_suite)
    ├── scenarios/         # YAML scenario definitions
    │   ├── calendar.yaml
    │   ├── companion.yaml
    │   ├── contacts.yaml
    │   ├── edge_cases.yaml
    │   ├── email.yaml
    │   ├── goals.yaml
    │   ├── memory.yaml
    │   ├── persona.yaml
    │   ├── prospecting.yaml
    │   ├── reminders.yaml
    │   ├── research.yaml
    │   ├── routing.yaml
    │   └── workflow.yaml
    └── results/           # JSON run outputs (timestamped)
        └── *.json
```

Problems with this layout:

1. `evals/` is not a package. `uv run python -m evals.runner` works only because
   the venv knows about the workspace root. There is no `pyproject.toml`, no
   declared deps, no version.
2. Infrastructure and data are colocated. `scenarios/` and `results/` sit next to
   Python source files. Running `make eval` writes output *into* the same directory
   as the library code.
3. The MCP server (`mcp_server.py`) is invoked as `uv run python evals/mcp_server.py`
   — a path reference, not a module reference. This breaks if the working directory
   changes.
4. All six dependencies (`httpx`, `asyncpg`, `pyyaml`, `mcp`, `langchain-mcp-adapters`,
   `anthropic`) are pulled from the workspace root's environment, not from an
   explicit requirement list. If the workspace drops one of those deps, the eval
   silently breaks.

---

## Target State

```
ze/
├── core/
│   └── ze-eval/               # NEW — eval infrastructure package
│       ├── pyproject.toml
│       └── ze_eval/
│           ├── __init__.py    # Public surface: ZeEvalClient, run_suite, load_scenarios
│           ├── types.py       # ScenarioResult, RunData, JudgeScore, SessionMetrics, VerifyResult
│           ├── scenario.py    # load_scenarios(), load_scenario_by_id()
│           ├── client.py      # ZeEvalClient
│           ├── judge.py       # LLM-as-judge (structured for DeepEval swap)
│           ├── verifier.py    # DB outcome verification
│           ├── metrics.py     # llm_cost_log session metrics
│           ├── scoring.py     # routing_correct(), tools_correct(), outcome_correct()
│           ├── runner.py      # run() orchestration
│           ├── report.py      # print_summary(), print_diff()
│           └── server.py      # MCP server (renamed from mcp_server.py)
└── eval/                      # NEW — test data and thin entrypoints
    ├── scenarios/             # YAML scenario files (moved from evals/scenarios/)
    │   └── *.yaml
    ├── results/               # JSON run outputs (moved from evals/results/)
    │   └── *.json
    ├── run.py                 # Entrypoint: python eval/run.py
    └── server.py              # Entrypoint: python eval/server.py
```

The old `evals/` directory is removed entirely after migration.

---

## Module Breakdown

### `ze_eval/types.py`

All dataclasses that cross module boundaries. Currently these are scattered as
inline dicts (e.g. `scenario_metrics`, `judge_score`, `verify_results`) in
`runner.py`. Promoting them to typed dataclasses makes the runner readable and
makes it possible to write tests against individual scorer functions.

```python
# core/ze-eval/ze_eval/types.py

@dataclass
class JudgeScore:
    quality: int           # 1–5
    tone: int              # 1–5
    tool_use: int | None   # 1–5 or None
    pass_: bool
    reasoning: str

@dataclass
class VerifyResult:
    table: str
    where: dict
    expect: str            # "exists" | "not_exists"
    actual_count: int
    passed: bool
    error: str | None

@dataclass
class SessionMetrics:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    llm_duration_ms: int
    llm_calls: int
    models: list[str]

@dataclass
class ScenarioResult:
    scenario_id: str
    scenario: dict
    ze_result: dict
    agent_used: str | None
    routing_correct: bool | None
    tools_correct: bool | None
    outcome_correct: bool | None
    verify_results: list[VerifyResult]
    latency_ms: int | None
    metrics: SessionMetrics | None
    judge: JudgeScore | None
    error: str | None

@dataclass
class RunData:
    run_id: str
    timestamp: str
    ze_url: str
    tag: str
    judge_model: str | None
    totals: dict
    by_agent: dict
    results: list[ScenarioResult]
```

### `ze_eval/scenario.py`

Scenario loading extracted from `runner.py` into its own module. The `scenarios_dir`
parameter defaults to the `eval/scenarios/` path relative to the repo root, but
callers (including the MCP server and tests) can pass a different path.

```python
def load_scenarios(
    tag: str = "",
    scenarios_dir: Path | None = None,
) -> list[dict]: ...

def load_scenario_by_id(
    scenario_id: str,
    scenarios_dir: Path | None = None,
) -> dict | None: ...
```

The MCP server currently discovers scenarios from a hardcoded relative path. With
this extraction, it calls `load_scenarios()` without knowing or caring where the
YAML files live.

### `ze_eval/judge.py`

Restructured for a clean DeepEval swap later. The `judge()` function signature stays
identical — callers do not change. Internally it calls OpenRouter directly (current
behaviour). The DeepEval adoption phase replaces this implementation only, touching
nothing else.

```python
async def judge(
    *,
    description: str,
    prompt: str,
    response: str,
    expected_agent: str | None,
    agent_used: str | None,
    criteria: list[str],
    model: str = DEFAULT_JUDGE_MODEL,
    api_key: str | None = None,
) -> JudgeScore: ...
```

When DeepEval is adopted (follow-up phase), this function will:
1. Build a `deepeval.test_case.LLMTestCase` from the inputs.
2. Run `GEval(name=..., criteria=criteria, ...)`.
3. Map the `GEval` score and reason back to `JudgeScore`.

The `JudgeScore` dataclass acts as the stable interface between the runner and
whatever judge implementation is active.

### `ze_eval/scoring.py`

The three scoring functions are pulled out of `runner.py` into their own module.
This makes them independently testable and removes the ~80-line scoring block from
the runner's main loop.

```python
def routing_correct(scenario: dict, agent_used: str | None) -> bool | None: ...
def tools_correct(scenario: dict, ze_result: dict) -> bool | None: ...
def outcome_correct(verify_results: list[VerifyResult]) -> bool | None: ...
```

`_match_args` becomes a private helper in this module.

### `ze_eval/runner.py`

The core loop stays structurally identical. With types and scoring extracted, the
main `run()` function shrinks from ~200 lines to ~100, importing from
`ze_eval.types`, `ze_eval.scenario`, `ze_eval.scoring`, `ze_eval.judge`,
`ze_eval.verifier`, and `ze_eval.metrics`.

The `results_dir` is no longer hardcoded to a relative path. It defaults to
`eval/results/` (via `RunnerConfig`), but callers can override it.

### `ze_eval/server.py`

Renamed from `mcp_server.py` to match the module naming convention. The MCP tools
(`ze_chat`, `ze_list_scenarios`, `ze_run_scenario`, `ze_run_suite`) are unchanged.
The `scenarios_dir` path is resolved via `ze_eval.scenario.load_scenarios()` so it
does not hard-code `evals/scenarios/`.

### `eval/run.py` and `eval/server.py`

Thin entrypoints at the repo root. All logic lives in `ze_eval`:

```python
# eval/run.py
from ze_eval.runner import main
main()
```

```python
# eval/server.py
from ze_eval.server import main
main()
```

Makefile targets update from `uv run python -m evals.runner` to
`uv run python eval/run.py` and from `uv run python evals/mcp_server.py` to
`uv run python eval/server.py`.

---

## Package Configuration

```toml
# core/ze-eval/pyproject.toml

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ze-eval"
version = "0.1.0"
description = "Eval infrastructure for Ze — runner, judge, verifier, MCP server"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "asyncpg>=0.29",
    "pyyaml>=6.0",
    "mcp>=1.0",
    "langchain-mcp-adapters>=0.0.9",
]

[tool.uv.sources]
# ze-eval has no Ze package dependencies — it talks to Ze over HTTP

[tool.hatch.build.targets.wheel]
packages = ["ze_eval"]
```

`ze-eval` deliberately has no dependencies on any `ze-*` package. It communicates
with Ze exclusively over the HTTP `/eval/chat` endpoint. This keeps it installable
in isolation for IDE integrations and keeps the dep graph clean.

---

## Dependency Graph

```
ze-eval   (no ze deps — talks to ze-api over HTTP)

ze-api    → ze-core, ze-sdk, all plugins        (unchanged)
eval/     → ze-eval                             (entrypoints only)
```

`ze-eval` does not appear in `ze-api`'s dependency list. The eval package is a
client of Ze, not a component of it.

---

## Makefile Changes

```makefile
# Before
eval:
    uv run python -m evals.runner

eval-judge:
    uv run python -m evals.runner --judge

eval-report:
    uv run python evals/report.py

eval-diff:
    uv run python evals/report.py --compare

eval-server:
    uv run python evals/mcp_server.py

# After
eval:
    uv run python eval/run.py

eval-judge:
    uv run python eval/run.py --judge

eval-report:
    uv run python eval/run.py report

eval-diff:
    uv run python eval/run.py report --compare

eval-server:
    uv run python eval/server.py
```

`report` is folded into `run.py` as a subcommand (`run.py report`) to keep the
entrypoint count low. Alternatively, a separate `eval/report.py` entrypoint is
fine — keep whichever is less surprising.

---

## Migration Steps

1. Create `core/ze-eval/pyproject.toml` and `core/ze-eval/ze_eval/` skeleton.
2. Add `ze-eval` to the workspace in the root `pyproject.toml` (`members` list).
3. Copy each source file from `evals/` to `ze_eval/`, applying the renames and
   refactors described above.
4. Create `eval/scenarios/` and `eval/results/` directories. Move the YAML files
   from `evals/scenarios/` and JSON files from `evals/results/`.
5. Write `eval/run.py` and `eval/server.py` thin entrypoints.
6. Update the Makefile.
7. Update `.claude/settings.json` MCP server config: change `evals/mcp_server.py`
   to `eval/server.py`.
8. Update `docs/eval.md` to reflect new paths, new `uv run` invocations, and
   `ze-eval` package location.
9. Delete `evals/`.
10. Run `make eval` and `make eval-judge` to confirm parity.

---

## Testing

`ze-eval` is infrastructure, not a Ze agent — it does not need the full Ze stack
to test its own logic. Unit tests cover:

- `ze_eval.scenario`: loading scenarios from a temp directory, filtering by tag,
  multi-turn detection, missing-field defaults.
- `ze_eval.scoring`: `routing_correct`, `tools_correct` (name-only and name+args
  variants), `outcome_correct` with mixed pass/fail results.
- `ze_eval.types`: dataclass round-trips to/from dict (for JSON serialisation).
- `ze_eval.report`: `print_summary` and `print_diff` on fixture run data.

Integration tests (requiring a live Ze server) remain in `make eval` / `make eval-judge`
as before.

---

## Documentation Impact

- `docs/eval.md` — rewrite all path references and `uv run` invocations. Add a
  section explaining that `ze-eval` is a standalone package under `core/ze-eval/`
  and that `eval/` holds the actual test data.
- `CLAUDE.md` — repository layout table: replace `evals/` row with `core/ze-eval/`
  and `eval/`. No other sections affected.
- `specs/README.md` — add Phase 53 row.

---

## Follow-up Phases

These are captured here as deferred scope. None are prerequisites for Phase 53.

### 53a — DeepEval judge adoption

Replace `ze_eval/judge.py`'s OpenRouter call with DeepEval's `GEval`. The public
`JudgeScore` dataclass and the `judge()` function signature do not change.
`GEval` supports the same natural-language `criteria` field already used in the
YAML scenario format.

The benefit: `GEval` independently reasons about each criterion with chain-of-thought
before scoring, instead of bundling all criteria into one prompt pass. Scores are
more consistent and the `reasoning` field is more specific.

Cost impact: effectively the same as today — one LLM call per judged scenario.

### 53b — Safety metrics

Add optional `make eval-safety` that runs `BiasMetric` and `ToxicityMetric` from
DeepEval against a configurable sample of scenarios (e.g. all `persona` and
`companion` tagged scenarios). These are referenceless metrics — they need only
`actual_output`, no retrieval context. They can be added to `ze_eval/judge.py`
as a secondary mode without touching the runner logic.

### 53c — Hallucination metrics for research agent

After the research agent is updated to surface its retrieved context in the eval
response (a `retrieval_context` field on the `/eval/chat` response), add
`HallucinationMetric` and `FaithfulnessMetric` from DeepEval for scenarios tagged
`research`. These metrics check whether Ze's response makes claims that contradict
the retrieved context.

This requires a change to `ze_api/api/routes/eval.py` to include retrieval context
in the response, and a change to `ze_eval/judge.py` to accept and pass it.

### 53d — Red teaming

Use DeepTeam (DeepEval's adversarial testing module) to run automated attack
suites against Ze. Relevant attack types:

- Jailbreak (forget-your-instructions variants)
- Persona corruption (role-play as a different assistant)
- PII extraction (repeat user's private data verbatim)
- Bias injection (steer Ze toward biased responses)

Red teaming runs are separate from `make eval` and do not block PRs. They are
best run weekly or before a production deployment.

### 53e — Synthetic scenario generation

Use DeepEval's `Synthesizer` to generate new YAML scenarios from Ze's user memory
contexts. The synthesizer takes a list of context strings (e.g. facts from the
`memory_facts` table) and generates plausible user prompts that exercise those
contexts. Output is reviewed before adding to `eval/scenarios/`.

This reduces the manual burden of writing YAML for new domains as Ze gains new
capabilities.

---

## Implementation Notes

- `ze_eval.scenario.load_scenarios()` must accept an explicit `scenarios_dir`
  argument so the MCP server, the runner, and future tests can all locate scenario
  files independently of working directory.
- `ze_eval.runner` writes results to `eval/results/<timestamp>.json` by default.
  The path is resolved relative to the repo root via the entrypoint, not hardcoded
  inside the package. Pass it as `results_dir` to `run()`.
- The `evals/__pycache__/` directory should be removed along with `evals/` in the
  migration step.
- The `.claude/settings.json` MCP server block currently points to
  `evals/mcp_server.py`. This must be updated in the same PR as the migration —
  it is what gives Claude Code its `ze_chat` / `ze_run_scenario` tools.

---

## Open Questions

- [ ] **Subcommand vs separate entrypoint for report**: `eval/run.py report` vs
  `eval/report.py`. Lean toward subcommand — fewer files to explain in docs.
- [ ] **`ze-eval` in the workspace `members` list**: Confirm whether `core/ze-eval`
  should be added to the root `pyproject.toml` workspace members. It should be,
  so `uv sync` installs it into the shared venv.
- [ ] **`eval/results/` gitignore**: JSON run results are currently not gitignored.
  Consider ignoring them or keeping a small curated set. Leaning toward ignoring
  (results are ephemeral; CI can upload them as artifacts if needed).
