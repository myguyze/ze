# Ze → Ze Core migration plan

This document is the **execution plan** for moving the production Ze application
(`packages/ze`) onto the framework (`packages/ze-core`). It complements:

- [`packages/ze-core/VISION_EVOLUTION.md`](../packages/ze-core/VISION_EVOLUTION.md) — rationale and long-term target architecture
- [`specs/zc-*.md`](../specs/) — framework contracts (interface, container, orchestration, etc.)

**Current state (baseline):** `ze` declares `ze-core` as a workspace dependency but
does not import `ze_core` yet. Ze still owns parallel copies of routing, capability,
memory, orchestration, goals, proactive, and telemetry. Telegram invokes
`graph.ainvoke()` directly via `ZeBot`, not `Container.invoke()`.

**Goal:** Ze runs on ze-core with **no user-visible regression**, Ze-specific code
lives only where it belongs (Telegram, Google, contacts, workflows, prospecting, …),
and `config.yaml` shrinks to behavioural preferences (~30 lines) with agent metadata
on `@agent` classes.

---

## Principles

1. **Incremental PRs** — each step leaves `main` deployable; prefer feature flags or
   dual wiring over big-bang rewrites.
2. **Prove with tests** — after every step: `make test` (ze) and `make test-core`.
3. **Framework vs application** — if it references Telegram, Gmail, or Ze-only tables,
   it stays in `packages/ze` (possibly calling ze-core primitives).
4. **Specs are law** — when behaviour is unclear, read the relevant `zc-*` spec before
   changing code.

---

## What stays in Ze (never moves to ze-core)

| Area | Location | Notes |
|------|----------|--------|
| Telegram transport | `ze/telegram/`, `ze/interface/telegram.py` (new) | Implements `AppInterface` |
| Multimodal preprocessing | `ze/telegram/preprocessor.py` (new) | Implements `InputPreprocessor`; Whisper + vision per `specs/19-multimodal-input.md` |
| Google OAuth / Calendar / Gmail | `ze/google/` | Application integrations |
| Contacts & prospecting | `ze/contacts/`, `ze/tools/prospecting.py` | Ze-specific data model |
| Workflow engine | `ze/workflow/`, `ze/orchestration/workflow_graph.py` | Separate graph; not ze-core conversation graph |
| Browser sidecar client | `ze-browser` package | Already extracted |
| Progress UX | `ze/progress/` | Telegram status messages |
| REST / eval API | `ze/api/` | Dev and ops surfaces |
| Reminders (user-facing) | `ze/reminders/` | App feature |
| Proactive job definitions | `ze/proactive/*.py` | Cron *times* in config; jobs call ze-core `ProactiveNotifier` |

---

## Schema and migrations

Ze today: `packages/ze/migrations/` (Alembic, 16+ revisions).  
Ze Core: `packages/ze_core/migrations/` (separate chain, 4 revisions).

**Do not switch Alembic roots mid-migration without a plan.**

Recommended approach:

1. **Until cutover:** Keep applying Ze migrations only (`make migrate` in `packages/ze`).
2. **Before first ze-core store in production:** Produce a **schema diff** (Ze DB vs
   ze-core `001`–`004`) and either:
   - add bridging migrations to ze-core that match Ze’s live schema, or
   - document that new ze-core-only tables (`capability_overrides`, etc.) are added via
     a single Ze migration that mirrors ze-core’s `004`.
3. **Cutover criterion:** One migration path, one source of truth — likely Ze’s Alembic
   tree importing SQL from ze-core revisions or merging histories in a dedicated “merge
   migration” PR.

Track progress in a checklist at the bottom of this file.

---

## Phases and steps

Phases follow `VISION_EVOLUTION.md` but are split into **reviewable PRs** with
acceptance criteria.

### Phase 0 — Prep (no behaviour change)

| Step | Work | Acceptance |
|------|------|------------|
| 0.1 | Add this doc; link from `docs/architecture.md` | Doc reviewed |
| 0.2 | Ensure CI runs `make test` + `make test-core` on every PR | Green CI |
| 0.3 | Inventory duplicate modules (`ze/*` vs `ze_core/*`); note intentional diffs (e.g. `plan_sequential`, workflow state fields) | Table in PR description or comment on this doc |
| 0.4 | Decide capability override story: keep `PUT /capabilities` via DB overrides (`ze_core.capability.overrides`) vs remove endpoint | Decision recorded in Phase 2 PR |

---

### Phase 1 — Interface seam (Telegram → ze-core entry points)

**Spec:** [`specs/zc-02-app-interface.md`](../specs/zc-02-app-interface.md), [`specs/zc-07-container.md`](../specs/zc-07-container.md)

Ze still uses its own graph for this phase; only the **transport boundary** changes.

| Step | Work | Acceptance |
|------|------|------------|
| 1.1 | Create `ze/interface/telegram.py` — `TelegramInterface` with `confirmation_style = "async"`, `send()`, `send_confirmation()`, `push()` | Unit tests with mocked Bot |
| 1.2 | Create `ze/interface/preprocessor.py` — `TelegramInputPreprocessor` (`RawInput` → `ProcessedInput`) | Covers text, voice, image per spec 19 |
| 1.3 | Thin `ZeBot`: build `RawInput`, call `container.invoke_raw()` / `container.resume()` instead of duplicating graph input dicts | One code path for normal messages |
| 1.4 | Move confirmation **delivery** to `send_confirmation()`; keep callback handlers writing state + `resume()` | Confirm flow unchanged in manual Telegram test |
| 1.5 | Wire `interface` and `preprocessor` on a ze-core `Container` subclass in `ze/container.py` (graph can still be Ze’s `build_graph` initially) | `validate_interface()` passes at startup |
| 1.6 | Goal redirect / edit-reply / persona keyboards: either stay in `ZeBot` as pre-invoke routing or grow `TelegramInterface` helpers — document choice | No regression on goal gates |

**Phase 1 done when:** Normal text message → `invoke_raw` → response; confirm button →
pause → callback → `resume` → response; proactive pushes use `interface.push()`.

**Implemented (2025-05):**

- `ze/interface/telegram.py` — `TelegramInterface` (`async` confirmation, `send`, `push`, `push_with_keyboard`)
- `ze/interface/preprocessor.py` — voice/image/text → `ProcessedInput`
- `ZeBot` — `_ingest_raw()` builds `RawInput`, preprocesses, runs graph; responses and capability confirmations go through the interface
- `ProactiveNotifier` — delegates to `TelegramInterface`
- `Container` — `validate_interface()` at startup; `make_graph_config()` helper
- Goal/plan/persona/contact callbacks remain in `ZeBot` (pre-invoke routing per step 1.6)

**Still for a follow-up PR:** call `ze_core.container.Container.invoke_raw()` / `resume()` from
`ZeBot` instead of hand-rolled `graph.ainvoke()` (requires a `ZeContainer` subclass with Ze’s graph and config).

---

### Phase 2 — Capability gate

**Spec:** [`specs/zc-03-capability-gate.md`](../specs/zc-03-capability-gate.md)

| Step | Work | Acceptance |
|------|------|------------|
| 2.1 | Replace `ze.capability.gate` imports with `ze_core.capability.gate` | `tests/capability/` pass |
| 2.2 | Remove `update_permanent()` and YAML loader from Ze; use class-level modes (stub until Phase 7) **or** wire `CapabilityOverrideStore` for API | `PUT /capabilities` behaviour decided in 0.4 |
| 2.3 | Pass `interface` in graph `config["configurable"]` for `await_confirmation` node (ze-core node) | Confirm still works end-to-end |

**Phase 2 done when:** No `ze.capability` package (or re-export only); gate has no Telegram imports.

---

### Phase 3 — Routing

**Spec:** [`specs/zc-04-routing.md`](../specs/zc-04-routing.md)

| Step | Work | Acceptance |
|------|------|------------|
| 3.1 | Switch `EmbeddingRouter`, `ComplexityEstimator`, `haiku_fallback` / `decompose` to ze-core | `tests/routing/` pass |
| 3.2 | Move routing thresholds out of `config.yaml` into ze-core defaults (override in code only if needed) | Config diff shows removed `routing:` block |
| 3.3 | Port **`plan_sequential`** into Ze as graph extension: use `graph_builder()`, add node + edge, do not fork ze-core `build_graph()` permanently | `test_plan_sequential_*` pass |

**Phase 3 done when:** Ze routing modules deleted or thin wrappers; sequential planning still works.

---

### Phase 4 — Memory

**Spec:** [`specs/zc-06-memory.md`](../specs/zc-06-memory.md)

| Step | Work | Acceptance |
|------|------|------------|
| 4.1 | Replace `ze.memory.store` with `PostgresMemoryStore` from ze-core | Memory API routes + tests pass |
| 4.2 | Replace consolidator / profile synthesis with ze-core; drop memory thresholds from `config.yaml` | Nightly consolidation unchanged |
| 4.3 | Fact approval UX: ensure `ConfirmationRequest` supports edit flow required by Ze | Multimodal + fact approval manual test |
| 4.4 | Contact proposals: pass `person_store` in `config["configurable"]` (ze-core hook already exists) | Contact extraction still runs |

**Phase 4 done when:** No `ze.memory` implementation files; `config.yaml` has no `memory:` section.

---

### Phase 5 — Goals & proactive

| Step | Work | Acceptance |
|------|------|------------|
| 5.1 | Switch goals store / planner / executor to ze-core | Goal agent + advance loop tests pass |
| 5.2 | Verification gates use `AppInterface` (not raw Bot) | Gate keyboard flow on Telegram |
| 5.3 | `ProactiveNotifier` uses `interface.push()` only | Remove aiogram from notifier |
| 5.4 | Keep Ze job modules (`briefing`, `insights`, `reminders`, …) but register via ze-core `ProactiveScheduler` | Scheduled jobs fire in dev |

**Phase 5 done when:** Proactive and goals have no parallel ze implementations.

---

### Phase 6 — Telemetry & persona

| Step | Work | Acceptance |
|------|------|------------|
| 6.1 | Switch `CostTracker` / `CostReconciler` / stores to ze-core | Costs command + API |
| 6.2 | Switch `PersonaStore` to ze-core; move persona profiles to `ze/persona.yaml` | Persona command unchanged |
| 6.3 | ContextVar helpers: import from `ze_core.telemetry` | No duplicate `ze.telemetry.context` |

**Phase 6 done when:** Telemetry and persona packages are ze-core + thin Ze wiring.

---

### Phase 7 — Agents: `@register` → `@agent`

**Spec:** [`specs/zc-01-agent.md`](../specs/zc-01-agent.md)

| Step | Work | Acceptance |
|------|------|------------|
| 7.1 | Migrate one pilot agent (e.g. `research`) to `@agent` + class attributes | Routing + gate read from class |
| 7.2 | Migrate remaining agents; delete `config/agents/` and `agents:` blocks in `config.yaml` | All agents in discovery scan |
| 7.3 | Replace `ze.agents.base` / `registry` with `ze_core.orchestration` (`BaseAgent`, `agent`, `tool`) | `bootstrap_agents` uses ze-core discovery |
| 7.4 | Port agentic loop / `call_tool` to ze-core `BaseAgent` APIs | Agent tool tests pass |

**Phase 7 done when:** Agent config lives only in Python classes; settings has no `agent_configs`.

---

### Phase 8 — Orchestration graph

**Spec:** [`specs/zc-05-orchestration.md`](../specs/zc-05-orchestration.md)

| Step | Work | Acceptance |
|------|------|------------|
| 8.1 | Replace `ze.orchestration.graph` with extended `graph_builder()` + ze-core nodes | Graph compile at startup |
| 8.2 | Merge `AgentState`: ze-core base + Ze workflow fields **or** keep workflow state only on `workflow_graph` | Checkpoint serde updated |
| 8.3 | Update checkpointer `allowed_msgpack_modules` to `ze_core.*` types | Restart + resume confirm works |
| 8.4 | Delete duplicate `ze/orchestration/nodes/*` except Ze-only extensions | Eval + orchestration tests green |

**Phase 8 done when:** Single conversation graph from ze-core; Ze only adds nodes/edges it owns.

---

### Phase 9 — Container, settings, cleanup

**Spec:** [`specs/zc-07-container.md`](../specs/zc-07-container.md)

| Step | Work | Acceptance |
|------|------|------------|
| 9.1 | `ZeContainer` subclasses `ze_core.container.Container`; `from_config()` discovers `ze/agents/` | Startup discovers all agents |
| 9.2 | `ZeSettings` extends ze-core `Settings`; Telegram/Google keys only on Ze side | `.env` template updated |
| 9.3 | Remove dead `ze/` modules (openrouter, routing, memory, … duplicates) | Grep shows imports only from `ze_core` |
| 9.4 | Final `config.yaml` ~30 lines (models, persona default, proactive crons) | Matches vision doc example |
| 9.5 | Update `docs/architecture.md`, `docs/configuration.md`, `CLAUDE.md` repo layout | Docs match tree |

**Phase 9 done when:** Ze is a thin application package on ze-core.

---

## Suggested PR order (minimum viable path)

```
0 prep → 1 interface → 2 capability → 3 routing → 4 memory
       → 5 goals/proactive → 6 telemetry/persona → 7 agents → 8 graph → 9 container
```

Phases **2–4** can be parallelized by different owners only after **1** lands (shared
`Container` and config wiring).

---

## Testing checklist (every phase)

- [ ] `make test` — Ze package
- [ ] `make test-core` — framework
- [ ] `make dev-poll` — manual: text, voice, image, confirm, cancel, edit draft
- [ ] `make dev-eval` — eval MCP path if orchestration touched
- [ ] Confirm graph resume after restart (checkpoint + `thread_id`)

---

## Success criteria (migration complete)

1. Ze production behaviour matches pre-migration (no intentional feature drops).
2. `packages/ze` has no duplicate implementations of ze-core primitives.
3. `config.yaml` ≤ ~30 lines of non-secret config; no per-agent YAML.
4. No Telegram/aiogram imports under `packages/ze-core/`.
5. Optional stretch: second small app on ze-core (validates framework generalization).

---

## Progress tracker

Update as PRs merge:

| Phase | Status | PR(s) | Notes |
|-------|--------|-------|-------|
| 0 Prep | ✅ | | Doc + architecture link |
| 1 Interface | 🟡 | | `TelegramInterface`, preprocessor, ZeBot `RawInput` path |
| 2 Capability | ⬜ | | |
| 3 Routing | ⬜ | | |
| 4 Memory | ⬜ | | |
| 5 Goals / proactive | ⬜ | | |
| 6 Telemetry / persona | ⬜ | | |
| 7 Agents `@agent` | ⬜ | | |
| 8 Orchestration | ⬜ | | |
| 9 Container / cleanup | ⬜ | | |
| Schema unified | ⬜ | | |

Legend: ⬜ not started · 🟡 in progress · ✅ done

---

## Open decisions (resolve before or during Phase 2)

1. **`PUT /capabilities`** — Remove, or keep via `CapabilityOverrideStore` (DB)?
2. **Checkpointer serde** — Big-bang module path change vs compat shim for old checkpoints?
3. **`image_data: bytes` in `AgentState`** — ze-core still allows bytes; vision doc prefers caption-only in state — align during Phase 8?

---

## References

| Document | Use |
|----------|-----|
| `packages/ze-core/VISION_EVOLUTION.md` | Why and target end state |
| `packages/ze-core/ZC_GAPS.md` | Framework gap list (currently all resolved) |
| `specs/zc-02-app-interface.md` | `AppInterface`, `invoke_raw`, confirmation |
| `specs/zc-07-container.md` | Discovery, DI, `invoke` / `resume` |
| `specs/19-multimodal-input.md` | Telegram preprocessor behaviour |
