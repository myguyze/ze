# ze-automation — Automation Substrate

> **Package:** `core/ze-automation` — `ze_automation/`
> **Status:** Done
> **Implemented in:** [Phase 74](../phases/074-automation-substrate/spec.md)

---

## Purpose

Owns the full automation stack: goals (multi-week autonomous execution), workflows
(multi-step scheduled plans), and accountability (anomaly detection, weekly narrative).
Extracted from `ze-personal` so the automation substrate has no dependency on contacts
or persona.

---

## Responsibilities

- **Goals** — `GoalStore`, `GoalPlanner`, `GoalExecutor`: create → plan milestones →
  execute milestone loop → verify gates → retrospective; `GoalSuggestionStore`: stores
  LLM-generated weekly proposals; `AccountabilityStore`: tracks execution anomalies
- **Workflows** — `WorkflowStore`, `WorkflowPlanner`, `WorkflowScheduler`: plan steps,
  schedule execution, handle failures and retries
- **Accountability** — `ActivitySummary`, `AnomalyRecord`, `build_narrative`: weekly
  synthesis of goal + workflow activity into a user-readable narrative with anomaly
  detection
- **Agents** — `GoalAgent`, `WorkflowAgent`: conversation agents for goal/workflow
  management, routing targets for automation-related messages
- **Jobs** — goal sweep, workflow sweep, accountability job, goal suggestion job
- Migrations — `zc` chain continuation (zc006–zc009, zc011, zc014)

---

## Out of Scope

- Persona and contacts — `ze-personal`
- Proactive job scheduling substrate — `ze-proactive`
- Memory writes from goal execution — `ze-memory`

---

## Module Location

```
core/ze-automation/ze_automation/
  goals/
    types.py            ← Goal, Milestone, Gate, GoalLearning
    store.py            ← GoalStore Protocol
    planner.py          ← GoalPlanner (LLM milestone + gate planning)
    executor.py         ← GoalExecutor (milestone execution loop)
    suggestion_store.py ← GoalSuggestionStore
    postgres_store.py   ← PostgresGoalStore
  workflow/
    types.py            ← Workflow, WorkflowStep
    store.py            ← WorkflowStore Protocol
    planner.py          ← WorkflowPlanner
    scheduler.py        ← WorkflowScheduler (APScheduler-backed)
    postgres_store.py   ← PostgresWorkflowStore
  accountability/
    store.py            ← AccountabilityStore Protocol
    types.py            ← AnomalyRecord, ActivitySummary
    narrative.py        ← build_narrative (LLM synthesis)
  agents/
    goal_agent.py       ← GoalAgent (@agent)
    workflow_agent.py   ← WorkflowAgent (@agent)
  jobs/                 ← goal, workflow, accountability proactive jobs
  runtime/              ← AutomationPlanner, AutomationStore contracts
  migrations/           ← zc continuation chain
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | `BaseAgent`, `@agent`, `@tool`, `LLMClient`, `DBPool` |
| `ze-proactive` | `ProactiveJob`, `ProactiveScheduler` |
| `ze-memory` | Memory read access for goal context |
| `ze-logging` | `get_logger` |

---

## Links

- [Phase 19 — Goal Engine](../phases/028-goal-engine/spec.md)
- [Phase 74 — Automation Substrate](../phases/074-automation-substrate/spec.md)
- [Phase 46 — Accountability Layer](../phases/046-accountability-layer/spec.md)
