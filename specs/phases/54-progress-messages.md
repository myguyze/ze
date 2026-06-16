# Phase 54 — Progress Messages

> **Status:** Done
> **Depends on:** Phase 49 (ze-sdk), Phase 37 (ze-news)

---

## Problem

Agents have `await self.emit(ctx, "research.searching")` calls throughout the codebase,
and locale YAML files exist at `ze-api/config/locales/`. But `ctx.reporter` is always
`None` in production — `ProgressReporter` is never constructed or injected, so every
`emit()` call is silently a no-op. Additionally:

- All progress translations live in `ze-api/config/locales/` — plugin authors must edit
  a central app file to add keys for their domain.
- The WebSocket `typing` frame (`{ type: "typing" }`) carries no text, so the UI can
  only show a generic spinner regardless of what Ze is doing.
- The news agent has no progress key for its long-running `refresh_news` fetch.

---

## Goals

1. Wire `ProgressReporter` end-to-end: each WebSocket turn creates one with a sink that
   sends `{ type: "typing", text: "..." }` frames, and passes it into the graph via
   `config_extra`.
2. Move locale files into each plugin as package data (`locales/en.yaml`,
   `locales/pt.yaml`). The `ZePlugin` base class provides a default `locale_data()`
   implementation that auto-loads from this convention.
3. Merge all plugin locale dicts at startup into one `ProgressTranslations`. The
   app-level `ze-api/config/locales/` files remain as an override layer (highest
   priority).
4. Extend the `typing` WebSocket frame to carry an optional `text` field. The UI shows
   it instead of a generic indicator when present.
5. Add `news.reading` and `news.fetching` progress keys. The `refresh_news` tool emits
   `news.fetching` mid-operation to keep the indicator alive during the RSS fetch.

---

## Architecture

```
Plugin.locale_data("pt")  ×N
       │
       ▼
ProgressTranslations.build(layers, fallback_layers)   ← built once at startup
       │ stored on ZeContainer.translations
       │
turns.py (per request)
       │ creates ProgressReporter(translations, sink=send_progress_frame)
       │ passes via config_extra["reporter"]
       ▼
_build_config → configurable["reporter"]
       │
execution.py → AgentContext.reporter
       │
BaseAgent.emit(ctx, "news.fetching")
       │
ProgressReporter.emit() → sink("📡 Fetching the latest news...")
       │
conn_mgr.send_frame({"type": "typing", "text": "📡 Fetching the latest news..."})
       │
WebSocket client → useChatSession → showTyping + typingText
```

---

## Changes

### `core/ze-agents/ze_agents/plugin.py`

Add `locale_data(locale: str) -> dict` to `ZePlugin`. Default implementation
auto-loads `locales/{locale}.yaml` from within the plugin's own package directory
(resolved via `cls.__module__`). Plugins following the convention need no override.

Add `_load_locale_file(locale: str) -> dict` classmethod as the shared loader.

### `core/ze-agents/ze_agents/progress/translations.py`

Add `ProgressTranslations.build(layers, fallback_layers)` classmethod that deep-merges
a list of dicts, later entries winning on conflict. Used to merge N plugin locale
dicts + one app-level override dict.

### Plugin locale files

Each plugin gains `locales/en.yaml` and `locales/pt.yaml` with its progress keys.
All existing content from `ze-api/config/locales/` migrates here:

| Plugin | Keys |
|---|---|
| `ze-personal` | `research.*`, `companion.*`, `goals.*`, `workflow.*` |
| `ze-calendar` | `calendar.*`, `reminders.*` |
| `ze-email` | `email.*` |
| `ze-prospecting` | `prospecting.*` |
| `ze-news` | `news.reading`, `news.fetching` |

### `apps/ze-api/ze_api/container.py`

Add `translations: Any` field to `ZeContainer`. Build it in `build_container()` by
merging all plugin `locale_data()` results, then applying the app-level
`config/locales/` files as an override layer. Locale is read from
`settings.config.get("locale", "en")`.

App-level `config/locales/en.yaml` and `config/locales/pt.yaml` become empty override
stubs — their content has migrated to plugins.

### `apps/ze-api/ze_api/api/websocket/turns.py`

Create a `ProgressReporter` per turn whose sink sends
`{ "type": "typing", "text": text }` frames. Pass it as `config_extra["reporter"]`
to `invoke_raw_turn`.

### `apps/ze-web/src/features/websocket/protocol.ts`

Extend the `typing` inbound frame: `{ type: "typing"; text?: string }`.

### `apps/ze-web/src/features/chat/hooks/useChatSession.ts`

Add `typingText: string | null` state. `useFrame("typing")` reads `frame.text` and
sets it. Expose `typingText` from the hook for the UI to render.

### `plugins/ze-news/ze_news/agents/agent.py`

Emit `"news.reading"` at the start of `run()`. Pass `reporter` through the `deps`
dict so tools can emit mid-operation.

### `plugins/ze-news/ze_news/agents/tools.py`

`refresh_news` accepts `reporter: Any = None`. Emits `"news.fetching"` before
calling `news_fetch_job.run(force=True)` so the typing indicator stays alive during
the multi-source RSS fetch.

---

## Locale key conventions

Keys follow `<domain>.<state>` dotted notation. Values are strings or lists (list →
random selection on each emit). Template args use `{name}` Python format syntax.

```yaml
news:
  reading:
    - "📰 Checking the headlines..."
  fetching:
    - "📡 Fetching the latest news..."
    - "🔄 Refreshing news sources..."
```

---

## Out of scope

- Push notification (ntfy) progress delivery — ntfy is for async delivery of final
  responses, not mid-turn status.
- Streaming responses — Ze uses `ainvoke` not `astream_events`; progress frames are
  the substitute for streaming status.
- Per-user locale selection — locale is a server-level setting for now.
- UI rendering of `typingText` beyond the text value — styling/animation is a UI
  concern and not specified here.
