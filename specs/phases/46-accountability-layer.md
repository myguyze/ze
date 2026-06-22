# Accountability Layer — Spec

> **Package:** `ze-personal` (job + status command), `ze-core` (anomaly hook)
> **Phase:** 46
> **Status:** Pending
> **Depends on:** Phase 9 (cost telemetry), Phase 7 (proactive scheduler), Phase 22 (agent harness)

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `AccountabilityJob` — weekly narrative | ✅ Done |
| `AccountabilityStore` — anomaly log table | ✅ Done |
| Cost anomaly detection in `ProactiveScheduler` | ✅ Done |
| Confirmation persistence + reconnect replay (bug fix) | ✅ Done |
| Confirmation timeout handling | ✅ Done |
| Confirmation ntfy on background | ✅ Done |
| `/status` introspection command | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze has 45 phases of capability. The binding constraint on becoming Jarvis is not more
features — it is trust. A solo user will only delegate real-world action if they can
confidently answer: "What did Ze do while I wasn't watching, and did it go wrong?"

This phase builds the accountability layer: the mechanisms that let Ze report on itself
to its principal without requiring the user to ask, and that surface silent failures
before they compound.

The layer has four parts:

1. **Weekly activity narrative** — a proactive job that sends a plain-language summary
   of what Ze did, what it spent, where it stalled, and what it is uncertain about.
2. **Cost anomaly surfacing** — per-agent cost outlier detection that fires a push
   notification when an agent run costs significantly more than its recent baseline.
3. **Confirmation flow hardening** — timeout handling and calibration audit so the
   approve/deny UX is actually usable day-to-day.
4. **`/status` on-demand introspection** — the same summary as the weekly narrative,
   but triggered by user message.

---

## Out of Scope

- A developer-facing log viewer or debugging dashboard.
- Streaming token output to the Flutter client (separate concern).
- Voice input (Phase 47 candidate — do not conflate with this phase).
- Multi-agent or multi-user accountability (single-user tool).
- LangSmith or external tracing integrations.

---

## Part 1: Weekly Activity Narrative

### Location

```
packages/ze-personal/
  ze_personal/
    jobs/
      accountability.py     ← AccountabilityJob (@proactive_job)
    accountability/
      __init__.py
      store.py              ← AccountabilityStore (anomaly log)
      types.py              ← ActivitySummary, AnomalyRecord
      summarizer.py         ← _build_narrative() — LLM call or template
```

### What `AccountabilityJob` does

Runs weekly (configured in `config.yaml`). Queries:

1. `llm_cost_log` for the past 7 days — grouped by agent, sum of `cost_usd` and
   `total_tokens`, count of runs.
2. `goals` + `goal_milestones` for active goals — which milestones advanced, which
   stalled (no `completed_at` and last activity > 3 days ago).
3. `workflow_runs` for any failures in the past 7 days (already queried by briefing via
   `PushLogStore.list_workflow_failures_within_hours`).
4. `accountability_anomalies` for any cost anomalies flagged in the past 7 days.

Builds a plain-language narrative (see `summarizer.py`) and delivers it via
`ProactiveNotifier` with `urgency="low"`.

Deduplicates against `PushLogStore` using key `"weekly_accountability"` with a 6-day
window so it does not double-fire if the scheduler retries.

### Data structures

```python
# ze_personal/accountability/types.py

from dataclasses import dataclass, field

@dataclass
class AgentCostSummary:
    agent: str
    run_count: int
    total_tokens: int
    cost_usd: float

@dataclass
class ActivitySummary:
    period_days: int
    agent_costs: list[AgentCostSummary]
    goals_advanced: list[str]           # milestone titles
    goals_stalled: list[str]            # goal titles with stalled milestones
    workflow_failures: list[str]        # workflow names
    anomalies: list[str]                # human-readable anomaly descriptions
    total_cost_usd: float

@dataclass
class AnomalyRecord:
    agent: str
    run_cost_usd: float
    baseline_cost_usd: float
    multiplier: float                   # run_cost / baseline
    session_id: str | None
    detected_at: str                    # ISO timestamp
```

### `AccountabilityStore`

Writes and reads from `accountability_anomalies` (see schema below). Used by both the
anomaly detection hook (Part 2) and the weekly job when building the narrative.

```python
# ze_personal/accountability/store.py

class AccountabilityStore:
    def __init__(self, pool) -> None: ...

    async def record_anomaly(self, rec: AnomalyRecord) -> None: ...

    async def list_anomalies_since(self, days: int) -> list[AnomalyRecord]: ...

    async def clear_older_than(self, days: int) -> None: ...
```

### `summarizer.py`

Builds the narrative as a template (no LLM call needed — the data is structured).
Falls back to a minimal "nothing notable" message when all lists are empty.

```python
# ze_personal/accountability/summarizer.py

def build_narrative(summary: ActivitySummary) -> str:
    """Return a plain-text Ze accountability narrative for the given summary."""
    ...
```

Example output (plain text, sent via ntfy):

```
Ze weekly report (last 7 days)

💸 Cost: $0.42 across 38 runs
   • research: 19 runs, $0.18
   • email: 12 runs, $0.14
   • prospecting: 7 runs, $0.10

🎯 Goals
   • Advanced: "Land 3 new clients" → milestone "Send 10 outreach emails" done
   • Stalled: "Write technical blog post" — no activity for 5 days

⚙️  Workflows: no failures

⚠️  Anomalies: prospecting agent spent $0.31 on one run (5× baseline) on 2026-06-09
```

---

## Part 2: Cost Anomaly Detection

### Where it runs

Inside `ProactiveScheduler` as a lightweight post-run hook, or as a scheduled job
running every 6 hours. The simpler path is a standalone `@proactive_job`:

```
ze_personal/jobs/cost_anomaly.py   ← CostAnomalyJob (@proactive_job)
```

### Logic

Queries `llm_cost_log` for the past 30 days, computes a per-agent rolling baseline
(median cost per run over the last 30 days, minimum 5 samples to establish a baseline).

For any run in the past 24 hours that costs more than `anomaly_threshold` × baseline,
record an `AnomalyRecord` and push a notification if one has not already been sent for
this session_id.

Default `anomaly_threshold: 4.0` (configurable in `config.yaml`).

Skips agents with fewer than 5 historical runs (no reliable baseline yet).

### Notification

```
⚠️ Ze anomaly detected

The prospecting agent spent $0.31 on one run — 5× its usual $0.06.
Session: abc123 | 2026-06-09 14:32
```

`urgency="high"`. No actions needed — this is informational.

---

## Part 3: Confirmation Flow Hardening

### Current state

The `await_confirmation` node in `ze_core/orchestration/nodes/execution.py` is a
stub — it fires after the graph resumes from `DRAFT` state and simply sets
`gate_decision = EXECUTE`. The actual confirmation prompt is sent in `draft_response`
(to be verified during audit). The `CONFIRM_TIMEOUT_SECONDS=900` env var exists.

### Current state (audited)

- Confirmations are sent as `{"type": "confirm_request", "id": ..., "prompt": ..., "actions": [...]}` frames
  via `conn_mgr.send_frame()` in `ze_api/api/ws.py:~202` after `container.invoke_raw_turn()` returns with
  `outcome.interrupted = True`.
- **Confirmed bug:** `confirm_request` frames are sent directly via the WebSocket and are never saved to
  `MessageStore`. The reconnect path (`ConnectionManager.connect()`) only replays `message_store.list_unread()`.
  A user who disconnects while a confirmation is pending reconnects to silence — the pending action is lost.
- `CONFIRM_TIMEOUT_SECONDS=900` exists as an env var but there is no `asyncio.wait_for` in
  `await_confirmation` — the graph waits indefinitely.
- Pending confirmations are not currently sent via ntfy when the app is backgrounded.

### Changes

**Confirmation persistence and replay (bug fix):** When `outcome.interrupted` is true, save the
`confirm_request` payload to a new `pending_confirmations` table keyed by `thread_id`. On WebSocket reconnect,
after replaying unread messages, query for any pending confirmation for the active thread and re-send the
`confirm_request` frame. Clear the row when the user responds or the timeout elapses.

```sql
-- ze-core migration zc017 (accountability_anomalies is zc014 in ze-automation)
CREATE TABLE pending_confirmations (
    thread_id    TEXT PRIMARY KEY,
    request_id   TEXT NOT NULL,
    prompt       TEXT NOT NULL,
    actions      JSONB NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Timeout handling:** Add `asyncio.wait_for` in `await_confirmation` using `CONFIRM_TIMEOUT_SECONDS`.
On timeout, send "I waited for your approval but the window elapsed — let me know if you'd like me to try
again." and delete the `pending_confirmations` row.

**ntfy on background:** When a `confirm_request` is about to be sent, also push an ntfy notification
with the prompt text and urgency `"high"`, so the user is paged if the app is closed. Wire this into the
same send path in `ze_api/api/ws.py`.

**Calibration:** Document the current DRAFT/EXECUTE boundary in `ze_core/capability/gate.py` as a
comment block so intent map changes don't silently alter confirmation behaviour.

---

## Part 4: `/status` On-Demand Introspection

### Routing

Handle as a WebSocket command frame (`{"type": "command", "name": "status"}`) in
`_handle_command()` in `ze_api/api/ws.py`, consistent with the existing `costs` command
(same file, same function). The Flutter app adds a dedicated button that sends this frame.

This is the correct pattern — not the input preprocessor and not an `intent_map` entry.
The `costs` command (already implemented) is the exact precedent: a named WS command
handled deterministically, bypassing the embedding router entirely. Natural language
variants ("what did you do today?") are out of scope for this phase.

### What it returns

The same data as `AccountabilityJob.run()` but for the past 24 hours (default) or 7
days if the user asks for a weekly summary. Calls `build_narrative(summary)` directly
and returns the result as a chat message.

No notification — this is a synchronous response to a user query.

---

## Database Schema

```sql
-- migration: 016_accountability_anomalies.sql

CREATE TABLE accountability_anomalies (
    id              BIGSERIAL PRIMARY KEY,
    agent           TEXT NOT NULL,
    run_cost_usd    NUMERIC(10, 6) NOT NULL,
    baseline_usd    NUMERIC(10, 6) NOT NULL,
    multiplier      NUMERIC(6, 2) NOT NULL,
    session_id      TEXT,
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_accountability_anomalies_detected_at
    ON accountability_anomalies (detected_at DESC);
```

---

## Configuration

```yaml
# config/config.yaml

proactive:
  accountability:
    schedule: "0 9 * * 1"          # Monday 09:00 weekly narrative
    cost_anomaly_schedule: "0 */6 * * *"  # every 6 hours
    anomaly_threshold: 4.0          # multiplier above baseline to alert
    anomaly_min_samples: 5          # min historical runs to establish baseline
    anomaly_retention_days: 30      # how long to keep anomaly records
    stall_days: 3                   # milestone idle days before counted as stalled
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_core.telemetry.postgres.PostgresCostStore` | Source for agent cost data |
| `ze_core.proactive.job.proactive_job` | Job registration |
| `ze_core.proactive.notifier.ProactiveNotifier` | Push delivery |
| `ze_core.proactive.push_log_store.PushLogStore` | Deduplication |
| `ze_personal.goals.store.GoalStore` | Stalled milestone detection |
| `ze_personal.workflow.store.WorkflowStore` | Workflow failure data |

---

## Implementation Notes

- `build_narrative` must never raise — catch all store errors and degrade gracefully
  (omit the section rather than crashing the job).
- The weekly narrative is not an LLM call. The data is structured; template it. This
  keeps it fast, free, and deterministic. An LLM rewrite pass is future scope.
- Cost anomaly detection uses median, not mean, to resist outlier distortion from the
  very anomalies we are trying to detect.
- The `/status` command must work even if `llm_cost_log` is empty (new install). Return
  "No activity recorded yet" rather than an error.
- Do not surface `session_id` raw in user-facing messages — it is internal noise. Only
  include date and agent name.

---

## Open Questions

- [x] **Confirmation replay on reconnect.** Confirmed bug: `confirm_request` frames are
  never saved to `MessageStore` and are not replayed on reconnect. Fixed in Part 3 via
  `pending_confirmations` table + reconnect replay + ntfy push.
- [x] **`/status` routing path.** Use `_handle_command()` in `ze_api/api/ws.py` as a
  named WS command (`{"type": "command", "name": "status"}`), consistent with the
  existing `costs` command. Not the input preprocessor; not an intent_map entry.
- [ ] **Anomaly threshold calibration.** `4.0×` is a guess. After 30 days of live use,
  revisit based on actual `llm_cost_log` data to tune for signal vs. noise.
