# Ze Architecture Assessment (Temporary)

> **Status:** Temporary working document — delete or promote to a spec once items are addressed.
>
> **Date:** 2026-06-15
>
> **Purpose:** Track architectural issues, tech debt, and structural improvements in priority order. Work through the [Top 5 action list](#top-5-fix-first) first, then remaining items by severity.

---

## How to use this document

1. Pick the next unchecked item from the action list or severity sections.
2. Fix it in a focused PR.
3. Mark the item done here (add `✅` and date) or remove it once resolved.
4. When all Critical/High items are done, delete this file or fold remaining notes into `docs/architecture.md`.

---

## Top 5 — fix first

| # | ID | Summary | Status |
|---|-----|---------|--------|
| 1 | C1 | Fix confirmation flow end-to-end (server interrupt → client UI → `resume_turn`) | ✅ 2026-06-15 |
| 2 | C2 | Lock down WS protocol contract (single source of truth + conformance test) | ✅ 2026-06-15 |
| 3 | H6 | Fix `cancel` command inverted logic / `None` dereference | ✅ 2026-06-15 |
| 4 | H1 + H2 | Remove plugin wiring from `ZeContainer` + add plugin dependency ordering | ✅ 2026-06-15 |
| 5 | H3 | Fix memory contradiction logic + entity scan scalability | ☐ |

---

## Critical

### C1. Confirmation (Approve/Deny) flow is broken end-to-end

- **Category:** Correctness
- **Location:**
  - `apps/ze-api/ze_api/api/ws.py:180-192, 259-302`
  - `apps/ze-web/src/screens/chat/ChatScreen.tsx:36-58`
  - `apps/ze-web/src/components/ConfirmComponent.tsx:11-15`
  - `apps/ze-api/ze_api/container.py:121-122` (`resume_turn` defined but never called from WS)
- **Issue:** When the graph interrupts before `await_confirmation`, the server sends `confirm_request`. The web client never handles `confirm_request` — user sees typing stop with no UI. The SDUI `ConfirmComponent` (embedded in `message.components`) sends `{type:"message", text:value}` on tap, which routes through `_handle_message` → `invoke_raw_turn` (fresh graph input) instead of `resume_turn` / `graph.ainvoke(None, config)`. `resume_turn` is dead code from the WS path.
- **Why it matters now:** Core safety mechanism for write actions (email, calendar, prospecting). Non-functional on the primary client.
- **Suggested fix:**
  1. Add typed outbound `confirm` frame to `protocol.ts`; handle `confirm_request` / `confirm_cancel` in client with inline confirm UI.
  2. Add server `confirm` frame branch calling `container.resume_turn(pending_config)` for approve; abort checkpoint for deny — do not reuse `_handle_message`.
  3. Wire or remove orphaned `resume_turn`.

---

### C2. WebSocket protocol contract diverges between server and client

- **Category:** Correctness / Tech debt
- **Location:** `apps/ze-api/ze_api/api/ws.py` vs `apps/ze-web/src/ws/protocol.ts`
- **Issue:**
  - **Confirm action key mismatch:** server emits `{label, payload}` (`ws.py:268-271`); client expects `{label, value, style}` (`protocol.ts:14-18`); `ConfirmComponent` reads `action.value` → `undefined`.
  - **Outbound commands:** TS union allows `"memory" | "contacts"` (`protocol.ts:42`) — server does not handle them (`ws.py:447`). Server handles `status`, `onboarding`, `reset`, `reset_preview` — absent from TS union.
  - **`component_submit`:** handled by server (`ws.py:171-178`) but missing from `OutboundFrame`.
  - **Onboarding metadata:** server attaches `onboarding` key on message frames (`ws.py:505-508`); TS types don't model it.
- **Why it matters now:** Protocol is the contract between two independently deployed units. Every drift is a runtime-only failure.
- **Suggested fix:** Generate TS types from a single source (JSON schema / Pydantic→TS codegen), or add server-side conformance tests against client fixtures. Make unions exhaustive.

---

## High

### H1. `ZeContainer` hard-codes plugin store types, defeating auto-discovery

- **Category:** Boundary violation / Scalability
- **Location:** `apps/ze-api/ze_api/container.py:68-86, 276-344`
- **Issue:** Container declares `goal_store / reminder_store / person_store / news_store: Any` and populates via per-plugin `try: import …; agent_deps.get(SpecificStore)` blocks. Also hand-builds `plugin_deps` listing every infra type. "Auto-discovered plugins" still require editing `container.py` in two places plus a typed field for REST routes.
- **Why it matters now:** `ze-finance` and `ze-legal` in progress; each will repeat this pattern.
- **Suggested fix:** Plugins expose REST stores via typed accessor (e.g. `plugin.rest_stores() -> dict[str, Any]`). Resolve route deps via plugin registry / FastAPI `Depends`. Register infra deps from a single declarative list. Remove `try/import` blocks.

---

### H2. Cross-plugin dependency and startup resolution is order-dependent

- **Category:** Correctness / Scalability
- **Location:**
  - `apps/ze-api/ze_api/bootstrap.py:57-79`
  - `apps/ze-api/ze_api/container.py:320-322, 261-267, 398-404`
- **Issue:** `discover_plugins` iterates entry points in importlib order. `agent_deps` accumulated in list order — cross-plugin deps only resolve if dependency plugin iterated first. Plugin `startup()` has same hazard (e.g. `CalendarPlugin` vs `PersonalPlugin` workflow executor).
- **Why it matters now:** Works today by luck of iteration order. Adding/renaming plugins can break startup.
- **Suggested fix:** Add `depends_on: tuple[str, ...]` to `ZePlugin`; topologically sort before dep accumulation and `startup()`. Fail loudly on cycles.

---

### H3. Memory contradiction logic is incorrect and won't scale

- **Category:** Correctness / Scalability
- **Location:** `core/ze-memory/ze_memory/retriever.py:391-412` (entity scans at `470-473, 566-607`)
- **Issue:** `_write_fact_with_contradiction_check` marks **every** prior fact sharing a predicate as contradicted — second `preferred_name` nukes all earlier values. Fetches all active facts and embeds every value per write (O(all_facts)). Full `memory_entities` table scans per episode/participant.
- **Why it matters now:** Corrupts user profile over time; degrades as facts accumulate.
- **Suggested fix:** Scope contradiction to (predicate, subject/entity) with similarity threshold. Push candidate filter into SQL. Replace full entity scans with indexed lookups; case-fold consistently (lookup lowercases, upsert keeps original casing → duplicates).

---

### H4. `PostgresMemoryStore` is a god object; `MemoryStore` protocol has drifted

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-memory/ze_memory/retriever.py:87-913`
  - `core/ze-memory/ze_memory/store.py:26-48`
  - `core/ze-memory/ze_memory/policies.py:63-108`
- **Issue:** One class owns retrieve-dispatch, all writes, consolidation SQL, graph side-effects, LLM promotion. Protocol omits methods callers use. Policies bypass protocol via `store._pool`.
- **Suggested fix:** Split into `MemoryReader` / `MemoryWriter` / graph-linker. Policies depend on narrow query interface. Align or drop Protocol.

---

### H5. React WS layer fragments chat state and broadcasts global "thinking"

- **Category:** Correctness / Scalability
- **Location:**
  - `apps/ze-web/src/ws/useWebSocket.ts:8-24, 62-71`
  - `apps/ze-web/src/messages/useMessages.ts`
  - `apps/ze-web/src/overlay/ContextOverlay.tsx:16-33`
- **Issue:** Three independent `useWebSocket` subscribers; overlay reimplements message handling in own `useState` (no thread filter, no `edit`/`ack`/error). `isThinking` is global — activity in one surface disables input in another. `lastFrame` written on every frame, read nowhere.
- **Suggested fix:** One frame dispatcher routing by `type`; single `useChat(threadId)` shared by chat and overlay; per-thread `isThinking`; delete `lastFrame`.

---

### H6. `cancel` command has inverted logic that dereferences `None`

- **Category:** Correctness
- **Location:** `apps/ze-api/ze_api/api/ws.py:373-378`
- **Issue:**
  ```python
  if name == "cancel":
      if pending_config is not None:
          await conn_mgr.send_frame({"type": "confirm_cancel", "id": ""})
          return None
      await container.abort_invocation(pending_config.get("configurable", {}).get("thread_id", ""))
  ```
  `abort_invocation` only reached when `pending_config is None` → `AttributeError` → connection teardown. Cancel never aborts in-flight invocation.
- **Suggested fix:** Invert: abort when active invocation; send `confirm_cancel` when confirmation pending. Guard `None`.

---

## Medium

### M1. Confirmation timeout doesn't abort paused LangGraph checkpoint

- **Category:** Correctness / Tech debt
- **Location:** `apps/ze-api/ze_api/api/ws.py:335-361`; `core/ze-core/ze_core/conversation.py:131-140`
- **Issue:** Timeout clears DB row and sends message; interrupted checkpoint left paused. Later messages hit ambiguous state.
- **Suggested fix:** On timeout/deny, clear/finalize checkpoint for thread.

---

### M2. Capability gate only checks primary subtask; resume re-runs as EXECUTE

- **Category:** Correctness
- **Location:** `core/ze-core/ze_core/orchestration/nodes/execution.py:24-33, 99-105`
- **Issue:** `capability_check` evaluates only `envelope.subtasks[0]`. `await_confirmation` unconditionally sets `GateDecision.EXECUTE` — `Mode.DRAFT_ONLY` intents can exceed ceiling after approval.
- **Suggested fix:** Per-subtask gate evaluation; re-evaluate (or branch DRAFT vs CONFIRM) on resume.

---

### M3. Single pre-route plugin hook silently drops others; dead routing branch

- **Category:** Scalability / Tech debt
- **Location:** `core/ze-core/ze_core/orchestration/graph.py:88-98`; `core/ze-core/ze_core/orchestration/edges.py:7-11`
- **Issue:** `pre_route_node()` wired via `next(...)` — only first plugin used. `build_graph` registers `"plan_sequential"` as `after_embed_route` destination that edge function never returns.
- **Suggested fix:** Compose/chain multiple pre-route nodes; remove dead branch.

---

### M4. `AgentState` mixes chat, workflow, and dynamic-plan concerns; three input factories drift

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-core/ze_core/orchestration/state.py:14-65`
  - `core/ze-core/ze_core/conversation.py:14-55`
  - `core/ze-core/ze_core/container.py:86-106`
  - `plugins/ze-personal/ze_personal/plugin.py:237-257`
- **Issue:** Workflow fields pollute every chat checkpoint. Three places construct initial state with different field sets. `state_extensions` unused. New state types require checkpoint serde allowlist edit (`apps/ze-api/ze_api/container.py:170-186`).
- **Suggested fix:** One `initial_state(partial)` factory; namespace workflow/plan fields via plugin `state_extensions`.

---

### M5. `_fetch_tool_executor_context` duck-types `RetrievalRequest` via `SimpleNamespace`

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-agents/ze_agents/base_agent.py:433-468`
  - `core/ze-core/ze_core/orchestration/nodes/context.py:44-56`
- **Issue:** Dependency inversion direction is correct (`ze-agents` can't import `ze-memory`), but `SimpleNamespace` + broad `except Exception` silently drops memory context on field drift. Duplicated in two places.
- **Suggested fix:** Define retrieval request as Protocol/TypedDict in `ze-agents`; have `ze-memory` accept it.

---

### M6. Fire-and-forget tasks swallow failures

- **Category:** Correctness / Testability
- **Location:**
  - `core/ze-core/ze_core/orchestration/nodes/memory.py:43-51, 83-87`
  - `core/ze-memory/ze_memory/retriever.py:167-169, 211-212, 435-436`
  - `apps/ze-api/ze_api/api/ws.py:290, 294`
- **Issue:** Episode writes, entity upserts, graph links via `asyncio.create_task` with internal `except Exception` — silent data loss possible.
- **Suggested fix:** Done-callbacks that log/raise, or bounded background queue with retry.

---

### M7. Sessions are a metadata overlay, not a first-class entity

- **Category:** Tech debt
- **Location:**
  - `apps/ze-api/ze_api/sessions/store.py:25-76`
  - `apps/ze-api/ze_api/api/routes/sessions.py:15-25`
  - `apps/ze-api/ze_api/api/ws.py:233-238, 250`
- **Issue:** One string under three names (`thread_id`, `session_id`, `sessions.id`). No FK ties sessions ↔ messages ↔ checkpoint ↔ memory episodes. `ws-{uuid}` orphan when client omits `thread_id`. REST list-only; no server-side create. Title never updates once set. `list_unread` ignores `thread_id` — reconnect replay mixes threads.
- **Suggested fix:** `Session` as authoritative entity with server-issued id; unify naming; scope unread replay by thread.

---

### M8. SDUI `ComponentRenderer` and frame handlers are non-exhaustive

- **Category:** Correctness / Tech debt
- **Location:**
  - `apps/ze-web/src/components/ComponentRenderer.tsx:13-25`
  - `apps/ze-web/src/screens/chat/ChatScreen.tsx:36-58`
  - `apps/ze-web/src/overlay/ContextOverlay.tsx:21-33`
  - `apps/ze-web/src/navigation/RefreshHandler.tsx:17`
- **Issue:** Component switch has no `default: never`; `catch { return null }` swallows render errors. Frame handlers are `if` chains with no exhaustiveness guard. Violates repo `typescript-exhaustive-switch` rule.
- **Suggested fix:** Add `never`-checked `default` cases; convert frame handling to exhaustive `switch`.

---

### M9. Onboarding has two `OnboardingError` types and unimplemented seed kinds

- **Category:** Tech debt / Correctness
- **Location:**
  - `core/ze-onboarding/coordinator.py:19-20`
  - `apps/ze-api/ze_api/errors.py:39-40`
  - `core/ze-onboarding/types.py:17-24`
  - `apps/ze-api/ze_api/onboarding/persistence.py:26-36, 50-68`
- **Issue:** Two distinct `OnboardingError` classes. `capability_request`, `contact`, `channel_connection` seed kinds declared but not handled. Profile-facet SQL duplicated with `retriever.py:855-872`.
- **Suggested fix:** Single `ZeError`-derived `OnboardingError`; implement or remove unsupported seed kinds; dedupe facet write through store.

---

## Low

| ID | Category | Location | Issue | Suggested fix |
|----|----------|----------|-------|---------------|
| L1 | Correctness | `apps/ze-api/ze_api/api/ws.py:102-107` | `try_set_busy()` outside lock — safe today (no await) but latent footgun | Document invariant or move under lock |
| L2 | Tech debt | `SettingsScreen.tsx:20-22`, `OnboardingFlow.tsx:28-30` | Raw `fetch` bypasses `api` client | Route through `lib/api.ts` |
| L3 | Tech debt | Per-screen inline types (e.g. `ContactsScreen.tsx:6-11`) | Duplicated API types | Shared `types/api.ts` |
| L4 | Correctness | `ChatScreen.tsx:76-84` | Optimistic user message ids may not reconcile with server | Reconcile on server ack |
| L5 | Tech debt | `apps/ze-api/ze_api/onboarding/reset.py:18-20` | Legacy memory tables in reset lists | Migration cleanup |
| L6 | Scalability | `core/ze-agents/ze_agents/base_agent.py:488-515` | `_truncate_messages` O(n²) re-serialization | Fine at current sizes; revisit if history grows |
| L7 | Tech debt | migrations `003` | `memory_episodes.session_id` / `memory_facts.source_episode_id` have no FK | Add FKs or document invariants |

---

## Testing gaps (highest-value coverage)

| Priority | Area | Would catch |
|----------|------|-------------|
| 1 | Confirmation flow E2E (server interrupt → frame → client → approve → resume) | C1, C2, H6 |
| 2 | WS protocol conformance test (server frames vs TS unions) | C2 permanently |
| 3 | Plugin discovery with shuffled entry-point order + cross-plugin deps | H2 |
| 4 | Memory contradiction/write paths | H3 regressions |
| 5 | Graph edges + compound capability | M2, M3 |
| 6 | React: `useMessages` thread filtering + frame dispatcher | H5, M8 |

**Note:** React app has vitest configured but zero test files today.

---

## Structural theme (cross-cutting)

The "core" layer has absorbed domain knowledge (workflow fields in `AgentState`, `person_store`/`persona_store` in `fetch_context`, `workflow_planner` in `plan_sequential`) and `container.py` has absorbed per-plugin knowledge. The plugin abstraction (`graph_nodes` / `graph_edges` / `state_extensions` / `agent_deps`) exists to prevent this but is underused. Pushing concerns back behind plugin hooks is the biggest structural lever before the next phase.

---

## What's working well (context)

- Layering discipline holds: no `ze_core` imports in plugins; `ze-sdk` re-export works.
- Typed-DI `_resolve()` in `bootstrap.py` is solid.
- Policy-per-module memory retrieval is a clean design.
- Onboarding core/app split is structurally sound.
- Constructor DI + dataclass domain types are consistently applied.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-06-15 | Initial assessment written |
