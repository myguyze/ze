# Automation Substrate — Spec

> **Packages:** `core/ze-automation/` (core), `core/ze-proactive/` (unchanged), `plugins/ze-personal/` (shrunk to persona + contacts only)
> **Phase:** 74
> **Status:** Done
> **Depends on:** Phase 47 ([47-plugin-framework.md](../047-plugin-framework/spec.md)), Phase 48 ([48-core-split.md](../048-core-split/spec.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| New `ze-automation` package boundary defined | ✅ Done |
| Types, store protocols, postgres impls extracted from `ze-personal` | ✅ Done |
| Migrations `zc006`–`zc009`, `zc011` moved to `ze-automation` | ✅ Done |
| `ze-proactive` kept separate as scheduling + delivery infrastructure | ✅ Done |
| SDK re-exports updated via `ze_sdk.automation` | ✅ Done |
| Planners and executors moved from `ze-personal` to `ze-automation` | ✅ Done |
| Goal and workflow agents moved to `ze-automation` | ✅ Done |
| `ze-api` wires `ze-automation` directly (not via plugin) | ✅ Done |
| `ze-personal` reduced to persona + contacts + onboarding only | ✅ Done |
| Tests updated for the new dependency graph | ✅ Done |

---

## Purpose

Goals and workflows are not incidental features of Ze. They are part of the product's
operating model: Ze does work over time, waits for checkpoints, schedules follow-up
actions, and preserves the history of those actions. That logic should not live behind
a plugin boundary — it is Ze's core.

The original Phase 74 scope extracted types, protocols, stores, and migrations out of
`ze-personal` into `ze-automation`. That was a necessary first step, but it stopped
short: planners, executors, and agents remained in `ze-personal`, which kept the plugin
as the de facto owner of automation behavior.

This phase completes the extraction. `ze-automation` becomes a first-class core package
that owns the full automation stack — types, persistence, planning, execution, and
agents. `ze-personal` is reduced to what only it can know: persona, contacts, and
onboarding. `ze-api` wires `ze-automation` directly, the same way it wires `ze-memory`
and `ze-core`.

`ze-proactive` does **not** merge into `ze-automation`. Scheduling, notification
delivery, and push deduplication remain a separate infrastructure layer.
`ze-automation` depends on `ze-proactive`; it does not absorb it.

---

## Responsibilities

- Own the complete automation stack as a Ze core package: types, store protocols,
  postgres implementations, planners, executors, schedulers, and agents.
- Own migrations for all goals and workflow tables.
- Register goal and workflow agents directly with `ze-api` — not via `ze-personal`.
- Keep `ze-proactive` as separate background-job infrastructure for cron/interval
  execution and proactive message delivery.
- Preserve the current user-visible behavior of goals and workflows during migration.
- Expose automation primitives through `ze-sdk` for plugin authors who build on top
  of goals and workflows.
- Leave `ze-personal` with only persona, contacts, and onboarding — no goals or
  workflow code.

---

## Out of Scope

- Merging `ze-proactive` into `ze-automation`.
- Making `ze-automation` a generic BPM engine for non-Ze use cases.
- Changing the public user experience of goals and workflows.
- Redesigning `ze-core` orchestration, routing, or capability gating.
- Renaming user-facing concepts away from "goals" and "workflows".
- Rewriting push delivery transport or notification channels.

---

## Module Location

```
core/ze-automation/
  ze_automation/
    goals/
      types.py
      store.py
      postgres.py
      suggestion_store.py
      planner.py           ← moved from ze-personal
      executor.py          ← moved from ze-personal
    workflow/
      types.py
      store.py
      postgres.py
      scheduler.py
      planner.py           ← moved from ze-personal
    agents/
      goals/               ← moved from ze-personal/agents/goals/
      workflow/            ← moved from ze-personal/agents/workflow/
    jobs/                  ← goal/workflow proactive jobs moved from ze-personal
    runtime/
      contracts.py
    __init__.py
    migrations/
      versions/

core/ze-proactive/
  ze_proactive/
    scheduler.py
    job.py
    notifier.py
    push_log_store.py

plugins/ze-personal/
  ze_personal/
    plugin.py              ← wires persona + contacts into the app; no goals/workflow
    contacts/
    persona/
    agents/
      companion/
      research/
    jobs/
      briefing/
      insights/
      contacts/
```

---

## Feature 1: `ze-automation` as Ze Core

### Problem

After the initial extraction (types, stores, migrations), planners, executors, and
agents still live in `ze-personal`. This means:

- Goals and workflows are "optional" from the architecture's perspective, even though
  they are not optional from the product's perspective.
- Changes to goal execution logic require touching the personal plugin.
- The personal plugin's `plugin.py` is burdened with goal/workflow wiring that does
  not belong there.

### Design

`ze-automation` owns the full automation stack:

- goal and workflow domain types,
- persistence protocols and postgres implementations,
- planning logic (GoalPlanner, WorkflowPlanner) with Ze-specific LLM prompts,
- execution logic (GoalExecutor) with state machine, gates, and replanning,
- scheduling (WorkflowScheduler),
- the GoalAgent and WorkflowAgent definitions,
- proactive jobs for goals and workflows.

`ze-api` wires `ze-automation` the same way it wires `ze-memory` — directly in
`container.py`, not through the plugin registry. Goals and workflows are always present;
they are not conditionally loaded.

`ze-personal` no longer contains any goals or workflow code. It owns:

- persona (identity, dials, profiles),
- contacts (person store, channel store, consolidation),
- onboarding,
- companion and research agent definitions,
- briefing, insights, and contact review jobs.

---

## Feature 2: Goals and Workflows as First-Class Ze Primitives

### Design

`ze-automation` exposes two coordinated subdomains:

- `goals/` for long-running objective tracking, replanning, and verification gates.
- `workflow/` for ordered step execution, scheduling, and result synthesis.

Both subdomains live entirely within `ze-automation`. There is no personal-plugin
adapter layer sitting between the automation engine and the rest of the app.

### Wiring

`ze-api/container.py` instantiates automation services directly:

```python
goal_store = PostgresGoalStore(pool)
goal_planner = GoalPlanner(client, memory_store, notifier, ...)
goal_executor = GoalExecutor(goal_store, goal_planner, notifier, ...)
workflow_store = PostgresWorkflowStore(pool)
workflow_planner = WorkflowPlanner(client)
workflow_scheduler = WorkflowScheduler(workflow_store, ...)
```

Agent registration happens via `ze_automation.agent_module_paths()` — a plain function
that returns the agent module paths, imported in `ze_api/container.py` alongside plugin
paths from `ZePlugin.agent_module_paths()`.

---

## Feature 3: Keep `ze-proactive` Separate

`ze-proactive` remains a standalone infrastructure package. The separation rule:

- `ze-proactive` answers "how do we run and deliver background work?"
- `ze-automation` answers "what long-running work exists and how does it execute?"
- `ze-personal` answers "who is this user, what do they know, and who do they know?"

If a component could reasonably be reused by a non-automation feature (calendar
reminder, news job), it belongs in `ze-proactive`.

If a component cannot exist without a goal or workflow abstraction, it belongs in
`ze-automation`.

If a component encodes persona, contact, or onboarding semantics, it belongs in
`ze-personal`.

---

## Feature 4: SDK Surface

`ze-sdk` continues to re-export automation types via `ze_sdk.automation` so plugin
authors who build features on top of goals and workflows have a stable import surface
without depending on `ze-automation` directly.

---

## Dependency Graph

### Before (original, pre-Phase 74)

```
ze-proactive   → ze-agents
ze-personal    → ze-sdk
ze-api         → ze-personal, ze-proactive, ze-core, ...
```

### After Phase 74 initial extraction (current state)

```
ze-proactive   → ze-agents
ze-automation  → ze-agents, ze-proactive, ze-memory
ze-sdk         → ze-agents, ze-proactive, ze-memory, ze-automation
ze-personal    → ze-sdk, ze-automation
ze-api         → ze-core, ze-sdk, ze-personal, ze-automation, ...
```

### After Phase 74 completion (target)

```
ze-proactive   → ze-agents
ze-automation  → ze-agents, ze-proactive, ze-memory
ze-sdk         → ze-agents, ze-proactive, ze-memory, ze-automation
ze-personal    → ze-sdk                              ← no ze-automation dep needed
ze-api         → ze-core, ze-sdk, ze-personal, ze-automation, ...
```

`ze-personal` no longer depends on `ze-automation` once goals and workflow code are
fully removed from it.

---

## Implementation Notes

- Do not move `ze-proactive` into `ze-automation`.
- Keep the public user vocabulary stable. This is an architectural move, not a product
  renaming.
- Move agent registration out of `PersonalPlugin.agent_module_paths()` for goals and
  workflows; add a top-level `ze_automation.agent_module_paths()` function instead.
- Proactive jobs for goals (stuck goal alerts, weekly narrative, goal suggestions) move
  with the executors and planners — they are automation concerns, not personal ones.
- Keep `ze-core` out of `ze-automation`.
- The goal and workflow base tables were always Ze core tables; their migrations already
  live in `ze-automation` after the initial extraction.
