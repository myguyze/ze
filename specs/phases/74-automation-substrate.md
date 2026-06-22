# Automation Substrate — Spec

> **Packages:** `core/ze-automation/` (new), `core/ze-proactive/` (unchanged), `plugins/ze-personal/` (shrunk)
> **Phase:** 74
> **Status:** Pending
> **Depends on:** Phase 47 ([47-plugin-framework.md](47-plugin-framework.md)), Phase 48 ([48-core-split.md](48-core-split.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| New `ze-automation` package boundary defined | 🔲 Pending |
| Goals/workflows shared substrate extracted from `ze-personal` | 🔲 Pending |
| `ze-proactive` kept separate as scheduling + delivery infrastructure | 🔲 Pending |
| SDK re-exports updated for automation authors | 🔲 Pending |
| Plugin wiring migrated to the new package boundary | 🔲 Pending |
| Tests updated for the new dependency graph | 🔲 Pending |

---

## Purpose

Goals and workflows are not incidental features of Ze. They are part of the product's
operating model: Ze does work over time, waits for checkpoints, schedules follow-up
actions, and preserves the history of those actions. Today, that logic is concentrated
inside `ze-personal`, which makes the personal plugin the de facto core of Ze's
automation story.

That is the wrong boundary. `ze-personal` should own user-specific semantics
(persona, contacts, personal prompts, assistant-specific jobs), but the reusable
automation substrate should live in a dedicated core package. This phase extracts
that substrate into `ze-automation` so goals and workflows become first-class Ze
primitives rather than plugin internals.

This phase is also explicit about one thing: `ze-proactive` does **not** merge into
`ze-automation`. Scheduling, notification delivery, and push deduplication remain a
separate infrastructure layer. `ze-automation` depends on `ze-proactive`; it does not
absorb it.

---

## Responsibilities

- Introduce a new `ze-automation` package as the canonical home for long-running
  Ze automation semantics.
- Move goal and workflow state machines, store protocols, planners, executors, and
  shared automation types into that package.
- Keep `ze-proactive` as separate background-job infrastructure for cron/interval
  execution and proactive message delivery.
- Preserve the current user-visible behavior of goals and workflows during migration.
- Expose automation primitives through `ze-sdk` so plugin authors do not need to
  depend on `ze-personal` directly for automation concepts.
- Reduce `ze-personal` to domain-specific wiring, prompts, onboarding, and user
  policy that sit on top of the shared automation substrate.

---

## Out of Scope

- Merging `ze-proactive` into the new automation package.
- Turning `ze-automation` into a general BPM/workflow engine for arbitrary external
  customers or non-Ze domains.
- Changing the public user experience of goals and workflows beyond internal package
  moves.
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
      planner.py
      executor.py
      suggestion_store.py
    workflow/
      types.py
      store.py
      planner.py
      scheduler.py
    runtime/
      contracts.py
      state.py
      prompts.py
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
    plugin.py                 ← wires `ze_automation` + `ze_proactive` into the app
    goals/                    ← shrunk to personal-specific adapters, if any remain
    workflow/                 ← shrunk to personal-specific adapters, if any remain
    agents/goals/
    agents/workflow/
    jobs/
```

---

## Feature 1: Shared Automation Substrate

### Problem

`ze_personal.goals` and `ze_personal.workflow` currently mix three different kinds of
code:

1. reusable automation primitives,
2. Ze-specific user-facing semantics,
3. plugin wiring and lifecycle integration.

That makes the package hard to evolve. Any change to goals or workflows drags the
personal plugin with it, even when the change is purely structural.

### Design

`ze_automation` becomes the shared substrate for:

- goal and workflow domain types,
- persistence protocols,
- planning interfaces,
- execution loops,
- execution state,
- reusable automation prompts and contracts.

The package should not know about contacts, persona, news, or any other personal
assistant domain. It is allowed to know about scheduling and notification interfaces
only through `ze-proactive`.

### Responsibilities of the new package

- Define the shared task/plan/run types used by both goals and workflows.
- Provide planner and executor interfaces that `ze-personal` can configure with
  Ze-specific prompts and policies.
- Own the store protocols for automation persistence.
- Own reusable execution state and checkpoint types.
- Own migration ownership for automation tables once the schema moves out of
  `ze-personal`.

### Implementation sketch

```python
# core/ze-automation/ze_automation/goals/types.py

@dataclass
class Goal: ...

@dataclass
class GoalMilestone: ...

@dataclass
class GoalGate: ...

@dataclass
class GoalLearning: ...

@dataclass
class GoalSuggestion: ...
```

```python
# core/ze-automation/ze_automation/workflow/types.py

@dataclass
class Workflow: ...

@dataclass
class WorkflowStep: ...

@dataclass
class WorkflowExecution: ...
```

```python
# core/ze-automation/ze_automation/runtime/contracts.py

class AutomationPlanner(Protocol):
    async def plan(self, prompt: str, **kwargs) -> list[Any]: ...

class AutomationStore(Protocol):
    ...
```

`ze-personal` keeps the concrete prompt text, product wording, and user-facing
assistant behavior. `ze-automation` keeps the mechanics.

---

## Feature 2: Goals and Workflows as First-Class Ze Primitives

### Problem

Goals and workflows are conceptually similar but operationally distinct:

- Goals span days or weeks, require check-ins, and evolve as work progresses.
- Workflows are stepwise automations, often one-shot or scheduled.

They share execution concepts, but they should not be forced into a single feature
shape just because they currently live in the same plugin.

### Design

`ze-automation` exposes two coordinated subdomains:

- `goals/` for long-running objective tracking, replanning, and verification gates.
- `workflow/` for ordered step execution, scheduling, and result synthesis.

The shared substrate should factor out common concepts:

- `TaskState` / `RunState`
- `PlanStep`
- `ExecutionOutcome`
- `VerificationRule`
- `ScheduleSpec`
- `ExecutionCheckpoint`

These are substrate concepts, not user-facing product concepts. `ze-personal` can map
them to assistant UX such as "start goal", "pause goal", or "run this workflow now".

### Migration boundary

The new package owns the reusable state machine and store contracts. `ze-personal`
retains:

- agent definitions,
- natural-language prompts,
- proactive job registration that is specific to the personal assistant,
- user-facing notifications and summaries,
- any domain-specific heuristics around personal memory, contacts, or persona.

---

## Feature 3: Keep `ze-proactive` Separate

### Problem

It is tempting to fold `ze-proactive` into `ze-automation` because goals and workflows
rely on scheduling and push notifications. That looks simpler on paper, but it conflates
two different layers:

- automation semantics: what should happen over time,
- proactive infrastructure: when to run jobs and how to deliver the notification.

If those are merged, the package boundary becomes too broad again.

### Design

`ze-proactive` remains a standalone infrastructure package providing:

- `ProactiveScheduler`
- `ProactiveJob`
- `ProactiveNotifier`
- `PushLogStore`

`ze-automation` depends on that package for runtime execution and user-facing delivery.
The dependency is one-way.

This gives the cleanest separation:

- `ze-proactive` answers "how do we run and deliver background work?"
- `ze-automation` answers "what long-running work exists?"
- `ze-personal` answers "how does Ze present that work to this user?"

### Rule

If a component could reasonably be reused by a non-automation feature such as a
calendar reminder or a news job, it belongs in `ze-proactive`.

If a component cannot exist without a goal/workflow abstraction, it belongs in
`ze-automation`.

If a component encodes personal-assistant semantics, it belongs in `ze-personal`.

---

## Feature 4: SDK and Runtime Wiring

### Problem

Today, plugin authors reach into `ze_personal` for automation-related abstractions
because that is where the concrete code lives. That makes `ze_personal` look like a
public foundation package even though it is semantically a plugin.

### Design

`ze-sdk` re-exports the automation substrate so plugin authors can depend on one
stable surface:

- automation types,
- planning/execution protocols,
- proactive job APIs,
- memory-safe shared contracts.

`ze-api` continues to assemble the app, but its plugin wiring should consume the new
package boundary rather than importing goals/workflows from `ze_personal`.

### Migration path

1. Move shared goal/workflow primitives into `ze-automation`.
2. Leave `ze-proactive` untouched.
3. Update `ze-personal` to import shared automation types from `ze-sdk` or
   `ze_automation`.
4. Re-export the new package through `ze-sdk`.
5. Remove direct `ze_personal.goals` / `ze_personal.workflow` imports from packages
   that only need the shared substrate.

---

## Dependency Graph

### Before

```
ze-proactive   → ze-agents
ze-personal    → ze-sdk
ze-api         → ze-personal, ze-proactive, ze-core, ...
```

### After

```
ze-proactive   → ze-agents
ze-automation  → ze-agents, ze-proactive, ze-memory
ze-sdk        → ze-agents, ze-proactive, ze-memory, ze-automation
ze-personal    → ze-sdk
ze-api         → ze-core, ze-sdk, ze-personal, ze-automation, ...
```

`ze-personal` should stop being the only place where Ze's long-running automation
concepts live. It becomes a consumer of the substrate, not the substrate itself.

---

## Implementation Notes

- Do not move `ze-proactive` into `ze-automation`; that would recreate the monolith
  under a new name.
- Keep the public user vocabulary stable. The refactor is architectural, not a product
  renaming exercise.
- Prefer thin compatibility re-exports in `ze_personal` during migration rather than a
  flag day that forces every import to change at once.
- Move database ownership with the code. If a table is owned by the automation substrate,
  its migration should live with the substrate, not in `ze-personal`.
- Keep `ze-core` out of the new package. This is a shared product substrate, not an
  engine concern.

---

## Open Questions

- Should `ze-automation` start as a thin facade over the existing `ze_personal.goals`
  and `ze_personal.workflow` modules, or should the move be a direct extraction?
- Should goal and workflow tables keep their current names, or should the schema be
  renamed to match the new package boundary?
- Should `ze-personal` keep compatibility imports for one release cycle, or should the
  codebase switch immediately to the new package?
- Should `ze-sdk` expose separate `ze_sdk.automation` and `ze_sdk.proactive` modules,
  or a single flattened automation surface?

