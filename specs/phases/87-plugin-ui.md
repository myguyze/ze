# Phase 87 — Plugin UI Platform

**Status:** Pending (87a–87c done)
**Depends on:** Phase 66 (Primitive UI), Phase 72 (API Client Codegen), Phase 75 (`@ze/ui`), Phase 76 (ze-api shell), Phase 82 (ze-web FSD)
**Architecture:** [arch/plugin-ui.md](../arch/plugin-ui.md)

**Packages touched:** `core/ze-plugin`, `core/ze-sdk`, `apps/ze-api`, `apps/ze-web`, `packages/ze-ui` (types only)

---

## What this is

Close the gap between Ze's backend plugin system and the React web client. Plugins gain
declarative hooks to contribute nav entries, settings sections, and management screens —
without editing `ze-web` for each new domain.

Delivery is split into sub-phases (87a–87d). Each sub-phase is independently shippable.
87e (optional frontend modules) is explicitly deferred.

---

## Architectural decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Contribution model | `ZePlugin.ui_contributions()` returning frozen dataclasses | Matches `webhook_handlers()`, `signal_sources()` collection pattern |
| Manifest endpoint | `GET /api/v0/ui/manifest` | Single fetch at app shell mount; reflects installed plugins |
| Management screens | Generic `PluginPage` + plugin REST endpoint returning SDUI | Reuses Phase 66 primitives; no per-plugin React page required |
| Nav icons | Lucide icon name strings in manifest | Backend cannot import React components; frontend maps names → components |
| Settings | `settings_operation_id` → dedicated REST endpoint | Live config; manifest is metadata-only |
| Page actions | Dual prefix: `rest:<operationId>` or bare/`msg:` → WebSocket | REST for mutations; WebSocket for agent-directed actions |
| Plugin REST | `ZePlugin.rest_routes() -> list[APIRouter]` | Completes Phase 76 sketch; collapses hardcoded routers in `app.py` |
| Core nav | Chat + settings hardcoded in ze-web | Settings must work before manifest fetch |
| Goals/workflows | Core-owned, not migrated | `ze-automation` is not a ZePlugin today |
| Tier 3 frontend | Deferred to 87e | Prove Tier 2 with one migrated page before npm module federation |
| Pilot migration | `ze_news` overview → Tier 2 | Smallest self-contained page; plugin already owns REST + data |

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `UiContribution` / `UiManifest` types (`ze_plugin/ui.py`) | ✅ Done |
| `ZePlugin.ui_contributions()` hook | ✅ Done |
| `collect_ui_contributions()` with dedup + core path guard | ✅ Done |
| `GET /api/v0/ui/manifest` | ✅ Done |
| Dynamic nav merge in `AppShell` | ✅ Done |
| `ze_sdk.ui` re-exports | ✅ Done |
| Generic `PluginPage` (87b) | ✅ Done |
| `rest_routes()` hook (87b) | ✅ Done |
| Settings sections (87c) | ✅ Done |
| Codegen types (87d) | 🔲 Pending |

---

| Sub-phase | Scope | Acceptance |
|-----------|-------|------------|
| **87a** | Types, collection, manifest endpoint, dynamic nav | Sidebar reflects manifest; duplicate path/id fails startup |
| **87b** | `rest_routes()` hook, generic `PluginPage`, page endpoint contract | `ze_news` page served without `pages/news` slice |
| **87c** | Settings section contributions | Plugin settings panel renders via SDUI |
| **87d** | Codegen: manifest types + icon map | `make codegen` updates `@ze/client` / `ze-web` generated stubs |
| **87e** | Optional `plugins/*/ui` npm packages | Deferred — spike only after 87b ships |

---

## Core contracts (`core/ze-plugin`)

### `ze_plugin/ui.py`

```python
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class UiContribution:
    """Declarative shell contribution from a plugin."""

    id: str
    """Stable identifier, e.g. 'ze_news.overview'."""

    plugin: str
    """Plugin name, e.g. 'ze_news'."""

    kind: Literal["nav", "settings_section"]
    label: str
    icon: str
    """Lucide icon name, e.g. 'newspaper'."""

    path: str | None = None
    """URL segment for nav entries, e.g. 'news'. None for settings-only."""

    page_operation_id: str | None = None
    """OpenAPI operationId for the page SDUI endpoint, e.g. 'getNewsPage'."""

    settings_operation_id: str | None = None
    """OpenAPI operationId for the settings SDUI endpoint, e.g. 'getNewsSettings'."""

    priority: int = 100
    show_in_mobile_nav: bool = True


@dataclass(frozen=True)
class UiManifest:
  nav: tuple[UiContribution, ...]
  settings_sections: tuple[UiContribution, ...]
```

### `ZePlugin` hook

```python
class ZePlugin(ABC):
    def ui_contributions(self) -> list[UiContribution]:
        """Shell contributions (nav, settings). Default: none."""
        return []

    def rest_routes(self) -> list:
        """FastAPI routers owned by this plugin. Default: none."""
        return []
```

### Collection (`ze_plugin/ui.py`)

```python
def collect_ui_contributions(plugins: list[ZePlugin]) -> UiManifest:
    """Merge contributions; raise AgentConfigError on duplicate id or nav path."""
    ...
```

Re-export via `ze_sdk.ui`.

---

## REST API (`apps/ze-api`)

### Manifest route

```
GET /api/v0/ui/manifest
```

| Field | Type | Description |
|-------|------|-------------|
| `nav` | `UiContribution[]` | Ordered nav entries (chat stays core-owned, not in manifest) |
| `settings_sections` | `UiContribution[]` | Ordered settings panels |

- `operation_id`: `getUiManifest`
- `response_model`: Pydantic schema in `ze_api/api/schemas.py` (REST boundary only)
- Auth: `require_api_key`
- Built at container startup; stored on `ZeContainer.ui_manifest`

### Page endpoint contract (per plugin)

Each nav contribution with a `page_operation_id` points at a plugin-owned route, e.g.:

```
GET /api/v0/news/page
```

Response:

```python
@dataclass
class PluginPageResponse:
    title: str
    tree: dict  # serialised Primitive tree — same shape as message.components
```

Plugins build trees with existing `ze_components` helpers. No new primitive types in 87a–87d.

### Settings endpoint contract (per plugin)

Each `settings_section` contribution with a `settings_operation_id` points at a plugin-owned
route, e.g.:

```
GET /api/v0/news/settings
```

Response: same `PluginPageResponse` shape (title + primitive tree). The manifest declares
**metadata only** — label, icon, operation ID. Live config (connection status, source lists,
upload state) is always fetched from the endpoint at render time.

Mutations from settings forms use plugin REST `POST`/`PATCH` routes, not WebSocket.

### Router mounting

`create_app()` replaces per-domain `include_router(news.router, …)` with:

```python
for plugin in container.plugins:
    for router in plugin.rest_routes():
        app.include_router(router)
```

Core routes (health, ws, memory, capabilities) remain in `ze-api`. Domain routes move to
plugins incrementally.

---

## Frontend (`apps/ze-web`)

### 87a — Dynamic nav

1. `features/load-ui-manifest/` — `useUiManifestQuery()` via `@ze/client`
2. `AppShell` merges core routes (chat, settings) with manifest `nav`
3. `shared/config/nav-routes.ts` keeps only **core-owned** entries; plugin nav is runtime
4. Icon resolver: `shared/ui/icons.ts` maps manifest strings → `lucide-react` components;
   unknown icons fall back to `Circle`

### 87b — Generic plugin page

```
pages/plugin-page/ui/PluginPage.tsx   # reads :path from URL, finds manifest entry, fetches page SDUI
widgets/plugin-screen/ui/PluginScreen.tsx
```

Route registration:

```ts
{ path: ":pluginPath", element: <PluginPage /> }  // after static routes, before catch-all
```

`PluginScreen` renders `ConnectedPrimitiveTree` with a **dual-prefix action router** (see
[Resolved decisions](#resolved-decisions)).

### 87c — Settings sections

`SettingsWorkspace` fetches `settings_sections` from manifest and renders each as a collapsible
section. Section body is loaded from the plugin's settings endpoint via `settings_operation_id`
(same `PluginPageResponse` shape). Forms submit to plugin REST routes; buttons use the same
`rest:` / bare action routing as management pages.

---

## SDK surface (`ze-sdk`)

```python
from ze_sdk.ui import UiContribution, UiManifest  # re-exports from ze_plugin.ui
```

Plugin authors never import `ze_plugin` directly.

---

## Example: ze_news migration (87b pilot)

**Before:** `pages/news`, `widgets/news-overview`, hardcoded nav in `nav-routes.ts`.

**After:**

```python
# plugins/ze-news/ze_news/plugin.py
class NewsPlugin(ZePlugin):
    def ui_contributions(self) -> list[UiContribution]:
        return [
            UiContribution(
                id="ze_news.overview",
                plugin="ze_news",
                kind="nav",
                label="News",
                icon="newspaper",
                path="news",
                page_operation_id="getNewsPage",
                show_in_mobile_nav=True,
            )
        ]

    def rest_routes(self) -> list[APIRouter]:
        return [news_router]
```

```python
# plugins/ze-news/ze_news/api/routes.py
@router.get("/news/page", operation_id="getNewsPage", ...)
async def get_news_page(...) -> PluginPageResponse:
    articles = await store.list_recent(...)
    return PluginPageResponse(title="News", tree=build_news_page(articles).to_dict())
```

`build_news_page()` composes `Col`, `Text`, `Badge`, `Table` primitives — no React.

Delete `pages/news` and `widgets/news-overview` after parity check.

---

## Codegen (87d)

Extend `scripts/codegen.ts`:

1. Fetch or parse OpenAPI for `getUiManifest` response → TypeScript types in `@ze/client`
2. Generate `apps/ze-web/src/generated/lucide-icons.ts` whitelist from known manifest icons
   (optional; manual map acceptable for 87a)

Update `make codegen` docs and `docs/frontend.md` — "Adding a plugin screen" becomes a
Python-only flow for Tier 2.

---

## Container wiring

In `build_container()`:

```python
ui_manifest = collect_ui_contributions(plugins)
# ...
return ZeContainer(..., ui_manifest=ui_manifest, plugins=plugins)
```

`create_app()` receives plugins list for router mounting (or reads from container at lifespan).

---

## Errors

| Condition | Behaviour |
|-----------|-----------|
| Duplicate `UiContribution.id` | `AgentConfigError` at startup |
| Duplicate nav `path` | `AgentConfigError` at startup |
| `page_operation_id` set but route missing from OpenAPI | Log warning; nav item hidden |
| Page endpoint 404/500 | `PluginScreen` shows `ErrorState` with retry |
| Unknown icon name | Fallback `Circle` icon |

---

## Testing

| Area | Tests |
|------|-------|
| `collect_ui_contributions` | Duplicate detection, ordering by priority |
| `GET /api/v0/ui/manifest` | Returns contributions from test plugin fixture |
| `GET /api/v0/news/page` | Returns valid primitive tree (schema validation via `@ze/ui` parse) |
| `ze-web` | AppShell renders dynamic nav from mocked manifest; PluginPage smoke test |

---

## Implementation order

1. **87a** — `ze_plugin/ui.py`, collection, manifest route, dynamic `AppShell` nav (keep
   existing hardcoded pages working in parallel)
2. **87b** — `rest_routes()`, news page endpoint + `build_news_page()`, generic `PluginPage`,
   mount news router via plugin
3. **87d** — codegen types (can parallel with 87b)
4. **87c** — settings sections
5. Remove hardcoded news nav entry once 87b verified
6. Incremental migration: contacts, reminders, costs (each optional follow-up PR)
7. **87e spike** — only if finance or another plugin hits SDUI limits

---

## Out of scope (this phase)

- Tier 3 npm plugin UI packages (87e)
- Migrating goals/workflows pages — these stay **core-owned** (see Resolved decisions)
- New SDUI primitives (charts, image galleries) — separate phase if needed
- Plugin-contributed chat commands or command palette
- WebSocket-driven live updates on plugin pages (polling/refetch is fine for v1)

---

## Resolved decisions

### Settings data shape

**Decision:** dedicated REST endpoint per settings section, referenced by `settings_operation_id`.

The manifest carries metadata only (label, icon, operation ID). Section content is fetched at
render time via e.g. `GET /api/v0/news/settings` → `PluginPageResponse`. This keeps the manifest
small, supports live config, and matches the page endpoint pattern.

### Goals / workflows pages

**Decision:** keep core-owned indefinitely.

Automation (goals, workflows) is wired directly by `ze-api` via `ze-automation`, not through a
`ZePlugin`. Migrating `/goals` would require an `AutomationPlugin` extraction with little
user-facing benefit. Phase 87 migrates plugin-owned domains (news, contacts, …) only.

### Action routing on plugin pages

**Decision:** dual-prefix routing in `PluginScreen` / settings section renderer.

| `button.action` prefix | Handler | Use case |
|------------------------|---------|----------|
| `rest:<operationId>` | `@ze/client` call → TanStack refetch of page/settings query | Idempotent UI mutations (refresh feed, toggle source, delete row) |
| bare or `msg:` | WebSocket `{ type: "message", text: action }` | Agent-directed actions ("Ask Ze to summarise these articles") |

Chat and onboarding keep their existing paths (`message`, `component_submit`). Plugin pages
prefer `rest:` for anything that mutates plugin state without involving the graph.

Example actions in SDUI:

```python
button("Refresh now", "rest:refreshNews")
button("Ask Ze about this", "msg:Summarise my unread news")
```

### Core nav in manifest

**Decision:** no — chat and settings stay hardcoded in `ze-web`.

Settings must work before the manifest can be fetched (connection config is pre-manifest).
Chat is the primary anchor surface and must not depend on plugin discovery. The manifest is
**additive**: core routes in `nav-routes.ts` + plugin `nav` entries merged at runtime in
`AppShell`.
