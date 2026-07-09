# Ze Eval — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| `POST /eval/chat` endpoint | ✅ Done |
| `ZeBot.invoke()` — graph invocation without Telegram | ✅ Done |
| `EvalChatRequest` / `EvalChatResponse` schemas | ✅ Done |
| MCP server (`evals/mcp_server.py`) | ✅ Done |
| HTTP client (`evals/client.py`) | ✅ Done |
| Scenario library (`evals/scenarios/`) | ✅ Done |
| Claude Code MCP configuration (`.claude/settings.local.json`) | ✅ Done |
| `make eval-server` Makefile target | ✅ Done |
| CLI runner (`evals/runner.py`) | ✅ Done |
| LLM judge (`evals/judge.py`) | ✅ Done |
| Report / diff tool (`evals/report.py`) | ✅ Done |
| Persistent results (`evals/results/`) | ✅ Done |
| Expanded scenario suite (calendar, email, goals, workflow, contacts, prospecting) | ✅ Done |
| `make eval`, `eval-judge`, `eval-report`, `eval-diff` targets | ✅ Done |
| Tool call assertions (`expected_tools` in scenarios, `tools_correct` metric) | ✅ Done |
| Tool call **argument** assertions (`args` in `expected_tools`, operator syntax) | ✅ Done |
| Outcome verification (`verify` blocks, DB checks via asyncpg, auto-cleanup) | ✅ Done |
| Latency and token tracking (wall-clock timing, `llm_cost_log` metrics, p95/avg/max) | ✅ Done |

---

## Purpose

Ze has unit tests for individual modules, but no end-to-end signal for whether Ze
actually behaves well as a whole. The eval system provides that signal by letting
any LLM-powered IDE (Claude Code, Cursor, Codex) interactively send messages to Ze,
inspect how it routed and responded, and use its own judgement to evaluate quality.

The key design choice: **the calling LLM is the judge**. There is no baked-in
scoring function. The eval system exposes Ze's behaviour as MCP tools; the IDE's
LLM reads the output and reasons about whether it is correct. This is more flexible
than a fixed rubric and naturally improves as the judge model improves.

---

## Out of Scope

- Voice and image eval (text-only via `POST /eval/chat`).
- Confirmation flow simulation — if Ze pauses for confirmation, `pending_confirmation`
  is returned in the response but no auto-resume is performed.
- Multi-user eval or isolated eval environments — Ze's database state (memory, routing
  log) is shared with the real user session. Eval threads are namespaced with
  `eval-<session_id>` thread IDs to limit contamination, but not fully isolated.

---

## Repository Layout

```
ze/
├── api/
│   └── routes/
│       └── eval.py              # POST /eval/chat
├── api/
│   └── schemas.py               # EvalChatRequest, EvalChatResponse, EvalRoutingInfo
└── telegram/
    └── bot.py                   # ZeBot.invoke() — core graph invocation
evals/
├── __init__.py
├── client.py                    # ZeEvalClient (async httpx wrapper)
├── judge.py                     # LLM-as-judge via OpenRouter (optional, --judge flag)
├── mcp_server.py                # FastMCP stdio server (interactive IDE mode)
├── report.py                    # CLI report and run-diff tool
├── runner.py                    # CLI eval runner (primary automation path)
├── results/                     # Persisted run JSON files (gitignored)
└── scenarios/
    ├── calendar.yaml            # Calendar read/write/delete/free-slot
    ├── companion.yaml
    ├── contacts.yaml            # Contact lookup, add, update, search
    ├── edge_cases.yaml
    ├── email.yaml               # Email read/compose/reply/summarise
    ├── goals.yaml               # Goal create/list/progress/milestone
    ├── memory.yaml
    ├── persona.yaml
    ├── prospecting.yaml         # Company research, outreach drafting
    ├── reminders.yaml
    ├── research.yaml
    ├── routing.yaml
    └── workflow.yaml            # Workflow create/list/pause/trigger
.claude/
└── settings.local.json          # MCP server wiring for Claude Code
```

---

## Data Flow

### CLI runner (primary)

```
make eval / make eval-judge
        │
evals/runner.py  ──── HTTP POST /eval/chat ────► ze/api/routes/eval.py
        │                                                  │
        │                                         LangGraph graph
        │                                                  │
        │                                    EvalChatResponse (JSON)
        │◄──────────────────────────────────────────────────┘
        │
        ├─ routing_correct check (always)
        │
        └─ [--judge] evals/judge.py ──► OpenRouter LLM
                                              │
                                    JudgeScore {quality, tone, tool_use, pass, reasoning}
                                              │
                          evals/results/<timestamp>.json
```

### Interactive IDE mode

```
IDE LLM (Claude Code / Cursor / Codex)
        │
        │  MCP tool call (ze_chat / ze_run_scenario / ze_run_suite)
        ▼
evals/mcp_server.py  ──── HTTP POST /eval/chat ────► ze/api/routes/eval.py
                                                              │
                                                     LangGraph graph
                                                              │
                                              EvalChatResponse (JSON)
                                                              │
        ◄─────────────────────────────────────────────────────┘
        │
   IDE LLM evaluates response against scenario criteria using its own reasoning
```

---

## API

### `POST /eval/chat`

**Auth:** `x-ze-api-key` header (same as the rest of the API).

**Request:**
```json
{
  "prompt": "What time is it?",
  "session_id": "eval"
}
```

`session_id` controls the LangGraph `thread_id` (namespaced as `eval-<session_id>`).
The same `session_id` across requests maintains conversation history. Use a fresh
`session_id` for each independent test.

**Response:**
```json
{
  "session_id": "eval",
  "response": "I don't have access to a real-time clock...",
  "agent_used": "companion",
  "routing": {
    "primary_agent": "companion",
    "confidence": 0.87,
    "routing_method": "embedding",
    "is_compound": false,
    "score_gap": 0.23,
    "raw_scores": { "companion": 0.87, "research": 0.64, "calendar": 0.41 }
  },
  "pending_confirmation": false,
  "error": null
}
```

---

## MCP Tools

Exposed by `evals/mcp_server.py` via the stdio MCP protocol.

| Tool | Description |
|------|-------------|
| `ze_chat(prompt, session_id?)` | Send one message to Ze, return structured JSON response |
| `ze_list_scenarios(tag?)` | List scenario definitions from `evals/scenarios/` |
| `ze_run_scenario(scenario_id)` | Run a named scenario, return response alongside criteria |
| `ze_run_suite(tag?)` | Run all scenarios, return per-scenario results + summary counts |

---

## Scenario Format

Each file in `evals/scenarios/` is a YAML list of scenario objects:

```yaml
- id: routing_research_factual         # unique identifier
  prompt: "What are the differences between PostgreSQL and MySQL?"
  description: "Clear factual research query — should route to research agent"
  expected_agent: research             # optional — enables routing accuracy check
  tags: [routing, research]            # for filtering via ze_list_scenarios / ze_run_suite
  criteria:                            # optional rubric hints for the evaluating LLM
    - Should be handled by the research agent
    - Should provide a substantive, accurate comparison
```

Add new scenarios by creating or editing YAML files. No code changes required.

---

## CLI Runner

`evals/runner.py` is the primary eval path. It does not require Claude Code.

```bash
make eval                      # routing accuracy only (cheap)
make eval-judge                # + LLM quality scores (costs tokens)
make eval-report               # show last run summary
make eval-diff                 # compare last two runs

uv run python -m evals.runner --tag routing        # filter by tag
uv run python -m evals.runner --judge --tag calendar
uv run python -m evals.report --compare
```

Each run saves a JSON file to `evals/results/<timestamp>.json` with:
- Per-scenario: `routing_correct`, `agent_used`, Ze's raw response, judge scores
- Aggregate: totals, per-agent breakdown, average quality/tone/tool_use

### Judge scores (when `--judge` is set)

The judge calls OpenRouter with the scenario criteria and Ze's response:

| Field | Type | Description |
|-------|------|-------------|
| `quality` | int 1–5 | Does Ze actually answer the question? |
| `tone` | int 1–5 | Is the tone appropriate and in character? |
| `tool_use` | int 1–5 or null | Did Ze use tools correctly? null if no tools involved |
| `pass` | bool | Would a real user be satisfied? |
| `reasoning` | str | One or two sentence explanation |

Default judge model: `anthropic/claude-haiku-4-5`. Override with `--judge-model`.

---

## Tool Call Assertions

Scenarios can declare `expected_tools` — a list of tool names (and optionally
expected arguments) that must be called **and succeed** for the scenario to pass
the tool check. This is objective and free (no LLM required).

### Short form (name-only)

```yaml
- id: calendar_read_today
  prompt: "What's on my calendar today?"
  expected_agent: calendar
  expected_tools: [list_events]    # Ze must call list_events successfully
```

### Long form (with argument assertions)

```yaml
- id: reminders_create_absolute
  prompt: "Remind me to call the dentist on Friday at 10am."
  expected_agent: reminders
  expected_tools:
    - name: set_reminder
      args:
        label__icontains: dentist   # label arg must contain "dentist" (case-insensitive)
```

Both forms can be mixed in the same scenario:

```yaml
expected_tools:
  - list_reminders                  # name-only — just check it was called
  - name: set_reminder
    args:
      label__icontains: dentist
```

The runner checks, for each declared tool:
1. A successful call to that tool name exists (`success: true`)
2. If `args` is declared, the args of the first matching successful call satisfy every
   declared condition

The result is stored as `tools_correct: true/false/null` per scenario and aggregated
as `tools_correct` and `tools_wrong` in the run totals.

**Semantics:**
- All listed tools must appear in `tool_calls` with `success: true`
- If a tool was called but failed (`success: false`), the assertion fails
- Arg conditions are applied to the args of the first successful call to that tool
- `null` = no `expected_tools` declared — tool check is skipped
- Tool names match exactly (no wildcards) — use the Python function name

### Arg condition operators

| Suffix | Match rule | Example |
|--------|-----------|---------|
| *(none)* | Exact equality | `label: dentist` |
| `__icontains` | Case-insensitive substring | `label__icontains: dentist` |
| `__contains` | Case-sensitive substring | `label__contains: Dentist` |
| `__gte` | Greater-than-or-equal (lexicographic) | `fire_at__gte: "2026-06-03"` |
| `__lte` | Less-than-or-equal (lexicographic) | `fire_at__lte: "2026-12-31"` |

`__gte` / `__lte` compare as strings. For ISO 8601 datetime strings this produces
correct chronological order. Do not use for numeric comparisons.

A condition fails if the arg key is absent from the actual call's args dict.

**Current coverage:** 33 of 85 scenarios have `expected_tools`. Scenarios where
the correct behaviour is to *not* call tools (e.g. graceful error handling,
ambiguous routing) intentionally omit `expected_tools`.

---

## Outcome Verification

`evals/verifier.py` connects directly to Ze's Postgres database via `asyncpg`
and runs declarative checks after each scenario executes. This closes the gap
between tool assertions (did Ze *call* the tool?) and actual persistence (did
the data land in the DB?).

```yaml
verify:
  - table: user_reminders
    where:
      label__icontains: dentist   # ILIKE '%dentist%'
      sent: false                 # exact boolean match
    expect: exists                # 'exists' or 'not_exists'
    cleanup: true                 # delete matching rows after check (default: true)
```

After checking, matching rows are deleted so eval runs don't contaminate each other.
`make eval-clean` handles any leftovers from interrupted runs.

### Supported condition operators

| Suffix | SQL | Example |
|--------|-----|---------|
| *(none)* | `= $n` | `status: planning` |
| `__icontains` | `ILIKE '%value%'` | `label__icontains: dentist` |

Boolean values (`true`/`false`) are rendered as `= TRUE` / `= FALSE` without a parameter.

### Verified tables

| Table | Scenarios | What's checked |
|-------|-----------|---------------|
| `user_reminders` | reminders_create_absolute, _relative, _multi_turn | label, sent=false |
| `workflows` | workflow_create_simple, _multi_step_approval | description keyword |
| `goals` | goals_create_simple, _multi_turn_define_and_confirm | objective keyword |
| `user_facts` | memory_store_explicit_fact, _recall_stored_fact | value keyword, contradicted=false |
| `contacts` | contacts_add_explicitly, _multi_turn_add_and_recall | name keyword |

Calendar and email scenarios do not have `verify` blocks because they write to
Google's APIs, not Ze's database.

**Current coverage:** 11 of 85 scenarios have `verify` blocks.

---

## Latency and Token Tracking

Each scenario run records two orthogonal latency signals:

| Signal | Source | What it measures |
|--------|--------|-----------------|
| `latency_ms` | `time.monotonic()` wall-clock | End-to-end HTTP round-trip including Ze graph execution |
| `llm_duration_ms` | `llm_cost_log.duration_ms` via `evals/metrics.py` | Cumulative LLM API time only (excludes DB, tool calls, routing) |

Wall-clock latency is always available. LLM-level metrics require:
1. A live Postgres connection (`DATABASE_URL` in env)
2. `set_flow_context("eval", session_id=...)` called in `eval.py` before `ze_bot.invoke()` — this tags `llm_cost_log` rows with the eval session_id

### `evals/metrics.py`

Queries `llm_cost_log` for a given session and returns `SessionMetrics`:

```python
@dataclass
class SessionMetrics:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    llm_duration_ms: int
    llm_calls: int
    models: list[str]
```

`fetch_session_metrics(session_id)` handles the double-prefix automatically:
`bot.invoke()` prepends `"eval-"`, so the stored session_id is `eval-{session_id}`.

### Cost note

`cost_usd` in `llm_cost_log` is backfilled by `CostReconciler` every 15 minutes.
Token counts and duration are available immediately. The eval runner uses token
counts rather than cost_usd to avoid timing dependencies.

### Aggregation

The runner collects:
- `latency_values` — raw per-scenario wall-clock ms (used for avg/p95/max)
- `total_tokens`, `prompt_tokens`, `completion_tokens` — summed across the run
- Per-agent `avg_latency_ms` — computed from `latency_sum_ms / total`

`evals/report.py` displays these in `print_summary()` and shows latency/token
deltas in `print_diff()`.

---

## Resolved Decisions

**Why not a fixed LLM judge?**
A fixed rubric requires knowing in advance what "correct" looks like. The eval
library doesn't know Ze's persona, current memory state, or instruction changes.
Delegating judgement to the calling LLM means evaluation improves automatically
as Ze's instructions change, and the evaluator can reason about context.

**Why is the judge optional?**
Routing accuracy is objective and cheap to compute. Running the full LLM judge on
every commit would be expensive and slow. The default `make eval` target gives fast
pass/fail signal on routing; `make eval-judge` is run on demand before significant
changes or releases.

**Why MCP rather than CLI only?**
An MCP server integrates directly into the IDE conversation. The evaluating LLM
can interleave tool calls (run a scenario, read the output, form a hypothesis,
run another scenario to test it) in the same context window where it is also
reading Ze's source code. This makes eval-then-fix loops possible in one session.
The CLI runner complements this for headless / CI use.

**Why not Telegram simulation?**
Constructing aiogram `Update` objects is brittle and tightly coupled to aiogram
internals. Invoking the LangGraph directly via `ZeBot.invoke()` tests everything
except the Telegram message parsing layer, which has no logic worth testing.

**Why namespace eval thread IDs?**
Eval runs share Ze's real database (memory, routing log). Prefixing thread IDs
with `eval-` ensures eval conversation history doesn't bleed into the user's
real conversation, and makes it easy to identify eval-originated entries in the
routing log.
