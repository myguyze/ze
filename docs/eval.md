# Ze Eval — Using the Eval System

Ze has two complementary eval modes:

- **CLI runner** (`make eval`) — standalone, no IDE required. Runs all scenarios,
  measures routing accuracy, and optionally runs an LLM quality judge. Results are
  stored in `eval/results/` as JSON so you can track trends and detect regressions.
- **MCP server** (`make eval-server`) — interactive mode for Claude Code / Cursor.
  The IDE's LLM acts as the judge and can run arbitrary prompts or named scenarios.

---

## Package layout

The eval system is split into two parts:

```
core/ze-eval/          # ze_eval Python package — all eval infrastructure
  ze_eval/
    __init__.py        # public surface: ZeEvalClient, load_scenarios
    types.py           # typed dataclasses: JudgeScore, VerifyResult, SessionMetrics, ScenarioResult
    scenario.py        # load_scenarios(), load_scenario_by_id()
    client.py          # ZeEvalClient — HTTP wrapper for /eval/chat
    judge.py           # LLM-as-judge (structured for DeepEval swap in a follow-up phase)
    verifier.py        # DB outcome verification
    metrics.py         # session token + latency metrics from llm_cost_log
    scoring.py         # routing_correct(), tools_correct(), outcome_correct()
    runner.py          # orchestration: load → run → score → print → save
    report.py          # print_summary(), print_diff()
    server.py          # MCP server: ze_chat, ze_list_scenarios, ze_run_scenario, ze_run_suite

eval/                  # test data and thin entrypoints
  scenarios/           # YAML scenario definitions — add new ones here
  results/             # JSON run outputs (gitignored, ephemeral)
  run.py               # CLI entrypoint
  server.py            # MCP server entrypoint
```

`ze_eval` is a standalone package with no Ze package dependencies — it communicates
with Ze exclusively over the `/eval/chat` HTTP endpoint.

---

## Prerequisites

- Ze server running locally: `make dev-eval`
- `ZE_API_KEY` from your `.env`

---

## Quick start (Claude Code)

The MCP server definition is committed in `.claude/settings.json` and available
to anyone who clones the repo. You only need to supply your API key once via a
local override file that is gitignored.

1. **Create `.claude/settings.local.json`** in the repo root with your key:
   ```json
   {
     "mcpServers": {
       "ze-eval": {
         "env": {
           "ZE_API_KEY": "<your ZE_API_KEY from .env>"
         }
       }
     }
   }
   ```
   This file is gitignored — it will never be committed.

2. **Start a new Claude Code session** (quit and reopen, or open a new terminal
   and run `claude` again). MCP servers start when the session starts; Claude Code
   merges `settings.json` and `settings.local.json`, with local winning.

3. **Start Ze** in another terminal: `make dev-eval`.

4. **Use the tools.** Ask Claude Code anything like:

   > "Run the `companion_greeting` scenario against Ze and tell me if the response is in character."

   > "Run the full routing suite and identify which scenarios Ze gets wrong."

   > "Send Ze the message 'remind me to call mum tomorrow at 6pm' and evaluate whether it handles the reminders correctly."

---

## Cursor / Codex / other MCP-compatible IDEs

Add the following to your IDE's MCP server config. The exact location varies:
- **Cursor**: `~/.cursor/mcp.json`
- **Codex CLI**: `~/.codex/mcp.json`

```json
{
  "mcpServers": {
    "ze-eval": {
      "command": "uv",
      "args": ["run", "python", "eval/server.py"],
      "cwd": "/path/to/ze",
      "env": {
        "ZE_EVAL_URL": "http://localhost:8000",
        "ZE_API_KEY": "<your ZE_API_KEY from .env>"
      }
    }
  }
}
```

Note the `cwd` field — unlike the Claude Code config (which runs from the project
root automatically), external IDE configs may need an explicit working directory.

---

## MCP Tools Reference

### `ze_chat`

Send a single message to Ze and get its response with routing metadata.

```
ze_chat(prompt="What time is it?", session_id="eval")
```

Returns:
- `response` — Ze's text response
- `agent_used` — which agent handled it (`companion`, `research`, `calendar`, etc.)
- `routing` — confidence, routing method, per-agent scores
- `pending_confirmation` — `true` if Ze paused to ask for user confirmation
- `error` — error message if the graph failed

Use the same `session_id` across calls to simulate a multi-turn conversation.
Use a fresh `session_id` for each independent test.

---

### `ze_list_scenarios`

List all available test scenarios.

```
ze_list_scenarios()                  # all scenarios
ze_list_scenarios(tag="routing")     # filtered by tag
```

Tags: `companion`, `routing`, `persona`, `research`, `calendar`, `email`,
`emotional`, `safety`, `compound`, `graceful_degradation`.

---

### `ze_run_scenario`

Run a named scenario and receive Ze's response alongside the scenario's
expected criteria. You (the evaluating LLM) read the criteria and judge whether
Ze's response passes.

```
ze_run_scenario(scenario_id="companion_greeting")
```

Returns the scenario definition, Ze's response, routing metadata, and a
`matches_expected_agent` boolean (if the scenario declares an `expected_agent`).

---

### `ze_run_suite`

Run all scenarios (or a filtered subset) in one call and get a summary.

```
ze_run_suite()               # all scenarios
ze_run_suite(tag="persona")  # persona scenarios only
```

Returns a summary with counts (`routing_correct`, `routing_wrong`, `errors`) and
per-scenario results for the evaluating LLM to review.

---

## The eval endpoint directly

If you prefer `curl` or want to integrate into your own script:

```bash
curl -X POST http://localhost:8000/eval/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-key>" \
  -d '{"prompt": "What is recursion?", "session_id": "test-1"}'
```

---

## Adding scenarios

Create or edit YAML files in `eval/scenarios/`. No code changes required.

### Single-turn scenario

```yaml
- id: my_new_scenario
  prompt: "The message Ze will receive"
  description: "What this is testing"
  expected_agent: companion          # optional — enables routing accuracy check
  expected_tools: [list_events]      # optional — tool names that must be called and succeed
  tags: [companion, persona]
  criteria:                          # optional rubric hints for the evaluating LLM
    - Should respond warmly
    - Should not use corporate language
```

`expected_tools` is a list of Python tool function names (e.g. `list_events`,
`create_event`, `set_reminder`, `draft_email`). All listed tools must appear in
the response's `tool_calls` with `success: true`. This check is objective and
free — no LLM judge needed. Omit it for scenarios where not calling tools is
correct behaviour (graceful errors, companion responses, ambiguous routing).

You can also add a `verify` block to check Ze's database directly after the
scenario runs:

```yaml
  verify:
    - table: user_reminders
      where:
        label__icontains: dentist   # ILIKE '%dentist%' — case-insensitive substring
        sent: false                 # exact boolean match
      expect: exists                # 'exists' or 'not_exists'
      cleanup: true                 # delete matching rows after check (default: true)
```

Verified rows are deleted after the check so eval runs don't contaminate each
other. Requires `DATABASE_URL` in your environment (same as Ze). Tables you can
verify against: `user_reminders`, `workflows`, `goals`, `memory_facts`, `contacts`.
Calendar and email write to Google's APIs, not Ze's DB, so they have no `verify` blocks.

### Multi-turn scenario

Use `turns` instead of `prompt` to send a sequence of messages in the same session:

```yaml
- id: my_multi_turn_scenario
  description: "What this sequence is testing"
  turns:
    - prompt: "First message to Ze"
      description: "Turn 1: establish context"
    - prompt: "Follow-up that depends on turn 1"
      description: "Turn 2: test context retention"
  expected_agent: companion          # checked against the last turn's agent_used
  tags: [companion, memory, multi_turn]
  criteria:
    - Turn 1 should do X
    - Turn 2 should reference turn 1 context
```

All turns in a multi-turn scenario share the same `session_id`, so LangGraph
conversation history is maintained between them.

Run `ze_list_scenarios()` to confirm it appears.

---

## CLI runner

```bash
make eval                      # routing accuracy only — cheap, no LLM judge
make eval-judge                # + LLM quality scores (costs tokens)
make eval-report               # show last run summary
make eval-diff                 # compare last two runs (regression detection)

# Fine-grained control
uv run python eval/run.py --tag routing          # filter by tag
uv run python eval/run.py --judge --tag calendar # judge calendar scenarios only
uv run python eval/run.py report --compare       # same as eval-diff
```

Results are saved to `eval/results/<timestamp>.json`. The judge uses
`OPENROUTER_API_KEY` from your `.env` and scores each response on:
- **quality** (1–5): Does Ze actually answer the question?
- **tone** (1–5): Is the tone appropriate and in character?
- **tool_use** (1–5 or null): Did Ze use tools correctly?
- **pass** (bool): Would a real user be satisfied?

---

## Latency and token tracking

Every scenario run captures two latency signals automatically — no extra config needed:

| Signal | Source | What it measures |
|--------|--------|-----------------|
| Wall-clock latency | `time.monotonic()` | End-to-end HTTP round-trip including graph execution |
| LLM duration | `llm_cost_log.duration_ms` | Cumulative LLM API time only (excludes DB, tool calls) |

The summary output shows:

```
  Latency (wall-clock)
    avg: 3.2s   p95: 7.8s   max: 12.1s

  Tokens (from llm_cost_log)
    total: 48,320   avg/scenario: 568
    prompt: 41,200   completion: 7,120
```

LLM-level metrics (tokens, `llm_duration_ms`) are available when `DATABASE_URL`
is set in your environment and Ze is running with Postgres. Token counts are
available immediately; `cost_usd` is backfilled asynchronously every 15 min by
`CostReconciler` and is not used by the runner.

`make eval-diff` shows latency and token deltas between runs:

```
  Avg latency:        3.2s → 2.9s (-0.3s)
  Total tokens:       48,320 → 45,100 (-3,220)
```

---

## Scenario coverage

| File | Scenarios | Focus |
|------|-----------|-------|
| `companion.yaml` | 5 | Greeting, emotional check-in, capabilities, graceful degradation, memory |
| `persona.yaml` | 5 | Sycophancy, honesty, refusal, tone, conciseness |
| `routing.yaml` | 6 | Routing accuracy across all agents, compound tasks |
| `research.yaml` | 6 | Research quality, coding questions, uncertainty, multi-turn |
| `reminders.yaml` | 7 | Create/list/cancel reminders, edge cases, multi-turn |
| `memory.yaml` | 6 | Fact storage, recall, contradiction handling, hallucination |
| `edge_cases.yaml` | 8 | Emoji-only, code paste, language switch, very long, topic switch |
| `calendar.yaml` | 9 | Read, create, delete, free slots, credential errors, multi-turn |
| `email.yaml` | 8 | Read, compose, reply, summarise, credential errors, multi-turn |
| `goals.yaml` | 7 | Create, list, progress check, milestone update, verification cadence |
| `workflow.yaml` | 6 | Create, list, pause, manual trigger, approval flow, error inquiry |
| `contacts.yaml` | 6 | Lookup, list, add, update, company search, multi-turn |
| `prospecting.yaml` | 6 | Company research, outreach draft, lead qualification, target lists |

Available tags: `companion`, `routing`, `persona`, `research`, `reminders`,
`memory`, `edge_case`, `multi_turn`, `emotional`, `safety`, `compound`,
`graceful_degradation`, `honesty`, `tone`, `conciseness`, `capabilities`,
`calendar`, `email`, `goals`, `workflow`, `contacts`, `prospecting`.

---

## Eval response fields

`ze_chat` and `ze_run_scenario` return these fields per turn:

| Field | Type | Description |
|-------|------|-------------|
| `response` | string | Ze's text response |
| `agent_used` | string | Which agent handled it |
| `routing` | object | confidence, routing_method, is_compound, score_gap, raw_scores |
| `pending_confirmation` | bool | True if Ze paused for user approval |
| `tool_calls` | array | Tools invoked: name, args, duration_ms, success, error |
| `tokens_used` | int | Total tokens consumed by the agent |
| `memory_proposals_count` | int | Explicit `AgentResult.memory_proposals` only (eval threads skip `write_memory` extraction) |
| `error` | string | Error message if the graph failed |

---

## Notes

- Eval threads are namespaced as `eval-<session_id>` to avoid contaminating the
  user's real conversation history, but they share the same database. Ze may surface
  user memory in eval responses.
- If `pending_confirmation` is `true`, Ze would normally pause for user approval.
  The eval endpoint returns the draft response in `response` and does not auto-resume.
- Calendar and email scenarios require valid Google credentials in `.env`.
  Without them, Ze should return a graceful error — that is itself a valid eval outcome.
- Reminders scenarios write real rows to the database. Clean up with
  `ze_chat("cancel all my reminders", session_id="cleanup")` after a suite run if needed.
- `eval/results/` is gitignored. Run results are ephemeral; copy notable runs
  elsewhere if you want to preserve them for comparison.
