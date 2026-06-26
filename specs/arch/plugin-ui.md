# Architecture: Plugin UI

**Status:** Active
**Related phases:** 66 (primitive UI), 75 (`@ze/ui`), 76 (`rest_routes` sketch), 82 (ze-web FSD), 87 (plugin UI platform)

---

## What this is

Ze's plugin system already extends the backend — agents, jobs, channels, webhooks, onboarding,
signal sources. The web client (`ze-web`) is still largely core-owned: nav routes, management
pages, and settings sections are hardcoded. A plugin that adds a domain (finance, legal, CRM)
cannot surface dedicated screens without editing `apps/ze-web`.

This document defines the **invariants** for plugin-contributed UI. Phase 87 describes
*how* to implement them.

---

## Design tiers

Plugin UI contributions fall into three tiers. **Higher tiers are opt-in; lower tiers must
always suffice for common cases.**

| Tier | Mechanism | Plugin author writes | Frontend deploy needed? |
|------|-----------|----------------------|-------------------------|
| **1 — SDUI** | Primitive trees (`@ze/ui`) | Python builders / render tools | No |
| **2 — Manifest + generic shell** | `UiContribution` + REST page endpoints | Python declarations + optional REST handlers | No |
| **3 — Frontend modules** | npm workspace package per plugin | TypeScript/React routes | Yes (bundled at build time) |

### Tier 1 — Server-driven UI (existing)

Agents and onboarding already emit primitive trees. Chat inline UI, onboarding forms, and
context overlays are Tier 1. Plugins contribute by calling render helpers from Python — no
new platform work required.

**Invariant:** The primitive vocabulary is fixed and small (Phase 66). New visual patterns
are composed in Python, not by adding React components to `ze-web`.

### Tier 2 — UI manifest + generic screens (new)

Plugins declare shell contributions (nav items, settings sections) via `ZePlugin.ui_contributions()`.
`ze-api` aggregates them into `GET /api/v0/ui/manifest`. Dedicated management screens use a
single generic `PluginPage` in `ze-web` that fetches a primitive tree from a plugin-owned
REST endpoint.

**Invariant:** The manifest reflects **installed Python plugins only**. There is no separate
frontend config that can drift from backend enablement.

**Invariant:** Manifest entries reference **stable string IDs** (`ze_news.overview`), not
import paths or React component names.

**Invariant:** Button `action` strings on plugin pages use explicit prefixes — never arbitrary
JS execution:

| Prefix | Handler |
|--------|---------|
| `rest:<operationId>` | `@ze/client` call, then refetch page/settings query |
| bare / `msg:` | WebSocket `message` frame to the agent |

Chat and onboarding keep their existing `message` / `component_submit` contracts unchanged.

### Tier 3 — Optional frontend modules (deferred)

When Tier 1+2 cannot express the interaction (charts, drag-and-drop, canvas editors), a
plugin may ship an optional `ui/` npm package discovered at codegen time. Tier 3 plugins
import only from `@ze/ui`, `@ze/client`, and `@ze/ui-shared` (public shell kit) — never from
`ze-web` internals or other plugins.

**Invariant:** Tier 3 is never required for a plugin to be useful. Core screens (chat, settings
shell) remain Tier 2 or core-owned.

---

## Relationship to existing extension points

| Concern | Existing hook | Tier |
|---------|---------------|------|
| Chat inline components | Agent render tools | 1 |
| First-run setup | `ZePlugin.onboarding()` | 1 |
| Progress/status copy | `ZePlugin.locale_data()` | — |
| Nav + management pages | *(none)* → `ui_contributions()` | 2 |
| Plugin REST API | `rest_stores()` today; `rest_routes()` in 87b | 2 |
| Settings panels | *(none)* → `settings_sections()` or SDUI page | 2 |
| Bespoke React screens | *(none)* → optional `ui/` package | 3 |

Onboarding is the reference implementation for Tier 2 interaction patterns: plugins declare
structured steps; the platform owns flow, rendering, and submission routing.

---

## Invariants

1. **Backend is source of truth.** What appears in the shell is derived from loaded plugins at
   startup, same as webhook handlers and signal sources.

2. **Duplicate IDs fail fast.** Two plugins registering the same `UiContribution.id` or nav
   `path` raise `AgentConfigError` at startup — mirror `signal_sources()` dedup.

3. **Codegen over hand-wiring.** Manifest TypeScript types and route stubs are generated
   (`make codegen`), like `@ze/client`. `ze-web` does not hardcode per-plugin nav entries
   after migration.

4. **REST before bespoke UI.** A plugin page endpoint returns data the client can render. Prefer
   SDUI composition server-side; reserve Tier 3 for genuine interaction limits.

5. **FSD boundaries hold.** Core `ze-web` stays thin. Plugin UI packages are isolated workspace
   packages with their own ESLint config importing only public kit APIs.

6. **Single user.** No per-user manifest caching, permissions UI, or marketplace discovery.

---

## Migration principle

Existing hardcoded pages (goals, news, contacts, …) are **not** blocked on plugin UI. Phase 87
ships the platform first; migration of individual pages is incremental. A page moves to Tier 2
when its plugin owns both the REST surface and the SDUI page builder.

**Core-owned surfaces (not migrated):** chat workspace, settings shell frame (connection +
data management), goals/workflows pages, onboarding wizard chrome, app shell layout.

Goals and workflows stay core-owned because `ze-automation` is wired directly by `ze-api`, not
via a `ZePlugin`. Only plugin-owned domains (news, contacts, finance, …) migrate to Tier 2.

## Settings sections

Settings contributions declare metadata in the manifest (`settings_operation_id`). Content is
always fetched from a dedicated plugin REST endpoint at render time — never embedded in the
manifest. Mutations use plugin REST routes; forms do not go through WebSocket.

## Core nav

Chat and settings are **not** manifest entries. They are hardcoded anchor routes in `ze-web`
because settings must work before manifest fetch succeeds. Plugin nav is additive.

---

## Out of scope

- Runtime plugin installation from the UI
- Multi-user / role-based UI visibility
- Arbitrary HTML/JS injection via manifest
- Replacing FSD in `ze-web` with a plugin folder inside the app
- General-purpose form/workflow engine beyond onboarding + SDUI actions
