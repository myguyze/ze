# Ze Architecture Assessment (Temporary)

> **Status:** Temporary working document — delete or promote to a spec once items are addressed.
>
> **Date:** 2026-06-15
>
> **Purpose:** Track architectural issues, tech debt, and structural improvements in priority order. Work through [Phase 4](#phase-4--fix-next) first, then remaining items by severity.

---

## How to use this document

1. Pick the next unchecked item from the [Phase 4](#phase-4--fix-next) table.
2. Fix it in a focused PR.
3. Mark the item done here (add `✅` and date).
4. When Phase 4 is complete, work through [Phase 5](#phase-5--polish--retirement) and delete or fold this file into `docs/architecture.md`.

---

## Phase 4 — fix next

| # | ID | Summary | Status |
|---|-----|---------|--------|
| 1 | H5 | Central WS frame dispatcher + shared `useChat(threadId)` hook | ✅ 2026-06-15 |
| 2 | M6 | Surface fire-and-forget memory write failures (done-callbacks or retry queue) | ✅ 2026-06-15 |
| 3 | H4 | Split `PostgresMemoryStore`; align `MemoryStore` protocol | ✅ 2026-06-15 |
| 4 | Tests | Plugin discovery order + memory write path regression tests | ✅ 2026-06-15 |
| 5 | L1–L7 | Low-severity polish batch (see [Low](#low--phase-4-5-batch)) | ☐ |

---

## Phase 5 — polish & retirement

| # | ID | Summary | Status |
|---|-----|---------|--------|
| 1 | M7 (remainder) | Unify `thread_id`/`session_id` naming; document or add FK invariants | ☐ |
| 2 | M4 (remainder) | Route `Container.invoke` through `make_graph_input()` (single factory everywhere) | ☐ |
| 3 | Doc | Delete this file or fold remaining notes into `docs/architecture.md` | ☐ |

> **After Phase 5 there are no planned phases.** Any new findings from `ze-finance` / `ze-legal` land as a fresh assessment or ad-hoc tickets — not a pre-defined Phase 6.

---

## Phase 3 — completed 2026-06-15

| # | ID | Summary |
|---|-----|---------|
| 1 | M5 | Typed `RetrievalRequest` in `ze-agents` (replace `SimpleNamespace`) |
| 2 | M3 | Compose pre-route plugin hooks; remove dead routing branch |
| 3 | M7 | Session hardening (orphan thread IDs, `POST /api/sessions`, title refresh) |
| 4 | M9 | Single `OnboardingError`; remove unimplemented seed kinds |
| 5 | M4 | Workflow fields moved to `WorkflowAgentState` via `state_extensions` |

---

## Phase 2 — completed 2026-06-15

| # | ID | Summary |
|---|-----|---------|
| 1 | M1 | Abort LangGraph checkpoint on confirmation timeout/deny |
| 2 | M2 | Per-subtask capability gate + correct resume semantics |
| 3 | H5 + M8 | Overlay-local thinking state + exhaustive frame/component switches |
| 4 | M7 | Scoped unread replay via `thread_id` on WS connect |
| 5 | C2 + tests | WS protocol conformance test + confirmation flow E2E coverage |

---

## Phase 1 — completed 2026-06-15

| # | ID | Summary |
|---|-----|---------|
| 1 | C1 | Confirmation flow end-to-end (server interrupt → client UI → `resume_turn`) |
| 2 | C2 | WS protocol type alignment |
| 3 | H6 | Cancel command inverted logic / `None` dereference |
| 4 | H1 + H2 | Plugin `rest_stores()` + topological plugin discovery ordering |
| 5 | H3 | Memory contradiction scoped to `(predicate, subject_id)` + indexed entity lookups |

---

## Critical

> **All Critical items resolved** in Phase 1–2.

### C1. Confirmation (Approve/Deny) flow is broken end-to-end ✅ Phase 1

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

### C2. WebSocket protocol contract diverges between server and client ✅ Phase 1–2

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

> **H1 ✅ · H2 ✅ · H3 ✅ · H5 ✅ (partial) · H6 ✅** — completed in Phase 1–2. **H4** — Phase 4 #3. **H5 (remainder)** — Phase 4 #1.

### H1. `ZeContainer` hard-codes plugin store types, defeating auto-discovery ✅ Phase 1

- **Category:** Boundary violation / Scalability
- **Location:** `apps/ze-api/ze_api/container.py:68-86, 276-344`
- **Issue:** Container declares `goal_store / reminder_store / person_store / news_store: Any` and populates via per-plugin `try: import …; agent_deps.get(SpecificStore)` blocks. Also hand-builds `plugin_deps` listing every infra type. "Auto-discovered plugins" still require editing `container.py` in two places plus a typed field for REST routes.
- **Why it matters now:** `ze-finance` and `ze-legal` in progress; each will repeat this pattern.
- **Suggested fix:** Plugins expose REST stores via typed accessor (e.g. `plugin.rest_stores() -> dict[str, Any]`). Resolve route deps via plugin registry / FastAPI `Depends`. Register infra deps from a single declarative list. Remove `try/import` blocks.

---

### H2. Cross-plugin dependency and startup resolution is order-dependent ✅ Phase 1

- **Category:** Correctness / Scalability
- **Location:**
  - `apps/ze-api/ze_api/bootstrap.py:57-79`
  - `apps/ze-api/ze_api/container.py:320-322, 261-267, 398-404`
- **Issue:** `discover_plugins` iterates entry points in importlib order. `agent_deps` accumulated in list order — cross-plugin deps only resolve if dependency plugin iterated first. Plugin `startup()` has same hazard (e.g. `CalendarPlugin` vs `PersonalPlugin` workflow executor).
- **Why it matters now:** Works today by luck of iteration order. Adding/renaming plugins can break startup.
- **Suggested fix:** Add `depends_on: tuple[str, ...]` to `ZePlugin`; topologically sort before dep accumulation and `startup()`. Fail loudly on cycles.

---

### H3. Memory contradiction logic is incorrect and won't scale ✅ Phase 1

- **Category:** Correctness / Scalability
- **Location:** `core/ze-memory/ze_memory/retriever.py:391-412` (entity scans at `470-473, 566-607`)
- **Issue:** `_write_fact_with_contradiction_check` marks **every** prior fact sharing a predicate as contradicted — second `preferred_name` nukes all earlier values. Fetches all active facts and embeds every value per write (O(all_facts)). Full `memory_entities` table scans per episode/participant.
- **Why it matters now:** Corrupts user profile over time; degrades as facts accumulate.
- **Suggested fix:** Scope contradiction to (predicate, subject/entity) with similarity threshold. Push candidate filter into SQL. Replace full entity scans with indexed lookups; case-fold consistently (lookup lowercases, upsert keeps original casing → duplicates).

---

### H4. `PostgresMemoryStore` is a god object; `MemoryStore` protocol has drifted — Phase 4 #3

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-memory/ze_memory/retriever.py:87-913`
  - `core/ze-memory/ze_memory/store.py:26-48`
  - `core/ze-memory/ze_memory/policies.py:63-108`
- **Issue:** One class owns retrieve-dispatch, all writes, consolidation SQL, graph side-effects, LLM promotion. Protocol omits methods callers use. Policies bypass protocol via `store._pool`.
- **Suggested fix:** Split into `MemoryReader` / `MemoryWriter` / graph-linker. Policies depend on narrow query interface. Align or drop Protocol.

---

### H5. React WS layer fragments chat state and broadcasts global "thinking" ✅ Phase 2 (partial)

- **Category:** Correctness / Scalability
- **Location:**
  - `apps/ze-web/src/ws/useWebSocket.ts`
  - `apps/ze-web/src/messages/useMessages.ts`
  - `apps/ze-web/src/overlay/ContextOverlay.tsx`
- **Done in Phase 2:** Removed `lastFrame`; overlay-local `thinking`; exhaustive switches in `ChatScreen` and `ComponentRenderer`.
- **Remaining (Phase 4 #1):** Central WS frame dispatcher; shared `useChat(threadId)` for main chat + overlay; overlay still maintains separate `useState<Message[]>` without thread filtering.
- **Suggested fix:** One frame dispatcher routing by `type`; single `useChat(threadId)` hook shared by chat and overlay.

---

### H6. `cancel` command has inverted logic that dereferences `None` ✅ Phase 1

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

> **M1 ✅ · M2 ✅ · M3 ✅ · M4 ✅ (partial) · M5 ✅ · M7 ✅ (partial) · M8 ✅ · M9 ✅** — completed in Phase 2–3. **M6** — Phase 4 #2. **M4/M7 remainder** — Phase 5.

### M1. Confirmation timeout doesn't abort paused LangGraph checkpoint ✅ Phase 2

- **Category:** Correctness / Tech debt
- **Location:** `apps/ze-api/ze_api/api/ws.py:335-361`; `core/ze-core/ze_core/conversation.py:131-140`
- **Issue:** Timeout clears DB row and sends message; interrupted checkpoint left paused. Later messages hit ambiguous state.
- **Suggested fix:** On timeout/deny, clear/finalize checkpoint for thread.

---

### M2. Capability gate only checks primary subtask; resume re-runs as EXECUTE ✅ Phase 2

- **Category:** Correctness
- **Location:** `core/ze-core/ze_core/orchestration/nodes/execution.py:24-33, 99-105`
- **Issue:** `capability_check` evaluates only `envelope.subtasks[0]`. `await_confirmation` unconditionally sets `GateDecision.EXECUTE` — `Mode.DRAFT_ONLY` intents can exceed ceiling after approval.
- **Suggested fix:** Per-subtask gate evaluation; re-evaluate (or branch DRAFT vs CONFIRM) on resume.

---

### M3. Single pre-route plugin hook silently drops others; dead routing branch ✅ Phase 3

- **Category:** Scalability / Tech debt
- **Location:** `core/ze-core/ze_core/orchestration/graph.py:88-98`; `core/ze-core/ze_core/orchestration/edges.py:7-11`
- **Issue:** `pre_route_node()` wired via `next(...)` — only first plugin used. `build_graph` registers `"plan_sequential"` as `after_embed_route` destination that edge function never returns.
- **Suggested fix:** Compose/chain multiple pre-route nodes; remove dead branch.

---

### M4. `AgentState` mixes chat, workflow, and dynamic-plan concerns ✅ Phase 3 (partial)

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-core/ze_core/orchestration/state.py`
  - `core/ze-core/ze_core/conversation.py`
  - `core/ze-core/ze_core/container.py`
  - `plugins/ze-personal/ze_personal/plugin.py`
- **Done in Phase 3:** Workflow fields moved to `WorkflowAgentState` via `PersonalPlugin.state_extensions()`; workflow executor uses `make_graph_input()`.
- **Remaining (Phase 5 #2):** `Container.invoke` still constructs graph input separately; checkpoint serde allowlist still manual.
- **Suggested fix:** Route all entry points through `make_graph_input()`; document serde allowlist convention.

---

### M5. `_fetch_tool_executor_context` duck-types `RetrievalRequest` via `SimpleNamespace` ✅ Phase 3

- **Category:** Coupling / Tech debt
- **Location:**
  - `core/ze-agents/ze_agents/base_agent.py:433-468`
  - `core/ze-core/ze_core/orchestration/nodes/context.py:44-56`
- **Issue:** Dependency inversion direction is correct (`ze-agents` can't import `ze-memory`), but `SimpleNamespace` + broad `except Exception` silently drops memory context on field drift. Duplicated in two places.
- **Suggested fix:** Define retrieval request as Protocol/TypedDict in `ze-agents`; have `ze-memory` accept it.

---

### M6. Fire-and-forget tasks swallow failures — Phase 4 #2

- **Category:** Correctness / Testability
- **Location:**
  - `core/ze-core/ze_core/orchestration/nodes/memory.py:43-51, 83-87`
  - `core/ze-memory/ze_memory/retriever.py:167-169, 211-212, 435-436`
  - `apps/ze-api/ze_api/api/ws.py:290, 294`
- **Issue:** Episode writes, entity upserts, graph links via `asyncio.create_task` with internal `except Exception` — silent data loss possible.
- **Suggested fix:** Done-callbacks that log/raise, or bounded background queue with retry.

---

### M7. Sessions are a metadata overlay, not a first-class entity ✅ Phase 3 (partial)

- **Category:** Tech debt
- **Location:**
  - `apps/ze-api/ze_api/sessions/store.py`
  - `apps/ze-api/ze_api/api/routes/sessions.py`
  - `apps/ze-api/ze_api/api/ws.py`
- **Done in Phase 2–3:** Scoped unread replay; client passes `threadId` in WS URL; `thread_id` required on messages; `POST /api/sessions`; `update_title` flag on upsert.
- **Remaining (Phase 5 #1):** `thread_id` / `session_id` / `sessions.id` naming still split; no FK ties sessions ↔ messages ↔ checkpoint ↔ memory episodes.
- **Suggested fix:** Unify naming in docs/code; document or enforce referential invariants (FKs optional for single-user scale).

---

### M8. SDUI `ComponentRenderer` and frame handlers are non-exhaustive ✅ Phase 2

- **Category:** Correctness / Tech debt
- **Location:**
  - `apps/ze-web/src/components/ComponentRenderer.tsx:13-25`
  - `apps/ze-web/src/screens/chat/ChatScreen.tsx:36-58`
  - `apps/ze-web/src/overlay/ContextOverlay.tsx:21-33`
  - `apps/ze-web/src/navigation/RefreshHandler.tsx:17`
- **Issue:** Component switch has no `default: never`; `catch { return null }` swallows render errors. Frame handlers are `if` chains with no exhaustiveness guard. Violates repo `typescript-exhaustive-switch` rule.
- **Suggested fix:** Add `never`-checked `default` cases; convert frame handling to exhaustive `switch`.

---

### M9. Onboarding has two `OnboardingError` types and unimplemented seed kinds ✅ Phase 3

- **Category:** Tech debt / Correctness
- **Location:**
  - `core/ze-onboarding/coordinator.py:19-20`
  - `apps/ze-api/ze_api/errors.py:39-40`
  - `core/ze-onboarding/types.py:17-24`
  - `apps/ze-api/ze_api/onboarding/persistence.py:26-36, 50-68`
- **Issue:** Two distinct `OnboardingError` classes. `capability_request`, `contact`, `channel_connection` seed kinds declared but not handled. Profile-facet SQL duplicated with `retriever.py:855-872`.
- **Suggested fix:** Single `ZeError`-derived `OnboardingError`; implement or remove unsupported seed kinds; dedupe facet write through store.

---

## Low — Phase 4 #5 batch

| ID | Category | Location | Issue | Suggested fix |
|----|----------|----------|-------|---------------|
| L1 | Correctness | `apps/ze-api/ze_api/api/ws.py` | `try_set_busy()` outside lock — safe today (no await) but latent footgun | Document invariant or move under lock |
| L2 | Tech debt | `SettingsScreen.tsx`, `OnboardingFlow.tsx` | Raw `fetch` bypasses `api` client | Route through `lib/api.ts` |
| L3 | Tech debt | Per-screen inline types | Duplicated API types | Shared `types/api.ts` |
| L4 | Correctness | `ChatScreen.tsx` | Optimistic user message ids may not reconcile with server | Reconcile on server ack |
| L5 | Tech debt | `apps/ze-api/ze_api/onboarding/reset.py` | Legacy memory tables in reset lists | Migration cleanup |
| L6 | Scalability | `core/ze-agents/ze_agents/base_agent.py` | `_truncate_messages` O(n²) re-serialization | Fine at current sizes; revisit if history grows |
| L7 | Tech debt | migrations `003` | `memory_episodes.session_id` / `memory_facts.source_episode_id` have no FK | Add FKs or document invariants |

---

## Testing gaps

| Priority | Area | Phase | Status |
|----------|------|-------|--------|
| 1 | Confirmation flow E2E | 2 | ✅ `test_ws_conformance.py` |
| 2 | WS protocol conformance | 2 | ✅ `test_ws_conformance.py` |
| 3 | Plugin discovery with shuffled entry-point order | 4 #4 | ✅ `test_plugin_discovery.py` |
| 4 | Memory contradiction/write paths | 4 #4 | ✅ `test_store_writes.py` |
| 5 | Graph edges + compound capability | 3 | ✅ M2 |
| 6 | Pre-route plugin composition | 3 | ✅ M3 |
| 7 | React: shared `useChat` + frame dispatcher | 4 #1 | ✅ 2026-06-15 |

**Note:** React vitest is configured but has no frontend test files yet.

---

## Structural theme (cross-cutting)

Phases 1–3 addressed correctness, plugin extensibility, and session/onboarding boundaries. **Phase 4** is structural cleanup before `ze-finance` / `ze-legal`: frontend WS consolidation (H5), memory observability (M6), memory store split (H4), missing tests, and low-severity polish. **Phase 5** closes partial stragglers (M4/M7 remainder) and retires this document.

After Phase 5, all pre-assessment findings are resolved. New plugin work may surface fresh items — track those separately, not as Phase 6.

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
| 2026-06-15 | Phase 1 completed (C1, C2 partial, H1, H2, H3, H6); Phase 2 backlog added |
| 2026-06-15 | Phase 2 completed (M1, M2, H5+M8, M7 partial, C2+tests); Phase 3 backlog added |
| 2026-06-15 | Phase 3 completed (M5, M3, M7, M9, M4); Phase 4 + Phase 5 backlog added |
| 2026-06-15 | Phase 4 #1 (H5): central `useFrame` dispatcher + `useChat(threadId)` hook; overlay thread filtering fixed |
| 2026-06-15 | Phase 4 #2 (M6): `fire_and_forget` utility in `ze_agents.tasks`; replaces bare `create_task` in memory, retriever, router, telemetry, ws |
| 2026-06-15 | Phase 4 #3 (H4): extracted `PostgresConsolidationStore`; aligned `MemoryStore` protocol; policies use `store.pool` via `MemoryQueryable` |
| 2026-06-15 | Phase 4 #4 (Tests): `test_plugin_discovery.py` topological sort; contradiction scoping tests in `test_store_writes.py` |
