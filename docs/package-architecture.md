# Ze — Package Architecture

Ze is a monorepo split into thirteen packages with a strict one-way dependency graph.
Understanding the split makes it clear where new code belongs and how the pieces fit.

---

## Packages

```
packages/
├── ze-core/          # Pure infrastructure — no domain knowledge
├── ze-memory/        # Memory package — facts, episodes, graph, retrieval
├── ze-personal/      # Personal-assistant domain layer
├── ze-email/         # Gmail channel + email agent (ZePlugin)
├── ze-prospecting/     # Prospecting agent, campaign store, recovery job (ZePlugin)
├── ze-calendar/      # Calendar + reminders domain (ZePlugin)
├── ze-google/        # Shared Google OAuth2 credentials (no Ze deps)
├── ze-news/          # News ingestion, ranking, credibility (ZePlugin)
├── ze-browser/       # Browser sidecar HTTP client
├── ze-notifications/ # Push notification abstraction (ntfy)
├── ze-components/    # Server-driven UI component descriptors
├── ze-api/           # Deployment unit — HTTP/WebSocket API, wires all plugins
└── ze-app/           # Flutter client app (iOS / Android / macOS / web)
```

### Dependency graph

```
ze-browser        ←  no ze deps
ze-core           ←  no ze deps
ze-notifications  ←  no ze deps
ze-components     ←  no ze deps
ze-google         ←  no ze deps
ze-memory         ←  ze-core
ze-personal       ←  ze-core, ze-memory
ze-email          ←  ze-core, ze-google, ze-personal
ze-prospecting    ←  ze-core, ze-browser, ze-personal
ze-calendar       ←  ze-core, ze-google, ze-personal
ze-news           ←  ze-core
ze-api            ←  ze-core, ze-memory, ze-personal, ze-email, ze-prospecting,
                      ze-calendar, ze-google, ze-browser, ze-news, ze-notifications,
                      ze-components
ze-app            ←  connects to ze-api over WebSocket (no Python deps)
```

This is a hard rule: `ze-core` never imports from any other Ze package. `ze-memory`
and `ze-personal` never import from `ze-api`. Violations break the abstraction and
make it impossible to reuse or test the infrastructure layer in isolation.

---

## ze-core — Pure Infrastructure

`ze_core` owns every primitive that is not specific to "Ze the personal assistant":

| Module | What it provides |
|--------|-----------------|
| `orchestration/` | LangGraph graph builder, `BaseAgent`, `@agent` decorator, node implementations, `AgentState`, `AgentContext`, hooks |
| `routing/` | `EmbeddingRouter`, `ComplexityEstimator`, `RoutingFallback` |
| `capability/` | `CapabilityGate`, `Mode`, `GateDecision`, `PostgresCapabilityOverrideStore` |
| `channels/` | `Channel` ABC, `ChannelRegistry`, `ChannelType`, `Message`, `SentMessage` |
| `interface/` | `AppInterface` ABC, `InputPreprocessor`, validation |
| `messages/` | `PostgresMessageStore`, `Message` types — conversation message persistence |
| `openrouter/` | `OpenRouterClient`, streaming, transcription |
| `telemetry/` | `CostTracker`, `CostReconciler`, `PostgresCostStore`, context vars |
| `proactive/` | `ProactiveScheduler`, `ProactiveNotifier`, `ProactiveJob`, `PushLogStore` |
| `progress/` | `ProgressReporter`, locale translations |
| `conversation.py` | `invoke_raw_turn`, `resume_turn` — entry points for the WS handler |
| `embeddings.py` | Shared `paraphrase-multilingual-MiniLM-L12-v2` singleton |
| `container.py` | Base `Container` with DI wiring, plugin support |
| `plugin.py` | `ZePlugin` ABC |
| `errors.py` | Typed exception hierarchy |

**Rule of thumb:** if you could imagine shipping `ze-core` as a standalone
"AI assistant framework" library and the feature would still make sense — it belongs
in `ze-core`. If it only makes sense for Ze's personal assistant use-case, it
belongs elsewhere.

---

## ze-memory — Memory Package

`ze_memory` owns all memory persistence, retrieval, and consolidation logic. It
depends on `ze-core` for logging and settings abstractions.

| Module | What it provides |
|--------|-----------------|
| `retriever.py` | `PostgresMemoryStore` — the central memory store implementing the full MemoryStore protocol |
| `consolidator.py` | `MemoryConsolidator` — nightly fact dedup, expiry, episode archival, profile synthesis |
| `extractor.py` | `gather_fact_proposals` — LLM-driven fact extraction from conversation turns |
| `policies.py` | `DefaultPolicyRegistry` — maps module names to retrieval policies |
| `projection.py` | Budget-aware result projection — `budget_facts`, `budget_episodes`, `facets_from_rows` |
| `types.py` | `Fact`, `Episode`, `Event`, `Procedure`, `TaskState`, `ProfileFacet`, `MemoryContext`, `RetrievalRequest` |
| `defaults.py` | Consolidation thresholds and retrieval defaults |
| `graph/store.py` | `PostgresGraphStore` — relationship storage and expansion |
| `graph/traversal.py` | `BoundedExpansionPolicy` — one-hop graph context enrichment |
| `graph/predicates.py` | Typed relationship predicates: `DESCRIBES`, `SOURCED_FROM`, `MENTIONS`, `BELONGS_TO_GOAL`, … |
| `graph/types.py` | `Relationship`, `GraphExpansion` |
| `graph/projection.py` | `enrich_context` — merge graph expansion results into `MemoryContext` |

---

## ze-personal — Domain Layer

`ze_personal` owns all personal-assistant domain logic. It depends on `ze-core` and
`ze-memory` but knows nothing about Google APIs or HTTP.

| Module | What it provides |
|--------|-----------------|
| `persona/` | `PostgresPersonaStore`, `build_identity_block`, named profiles, dial overrides |
| `contacts/` | `PersonStore`, `ContactChannelStore`, extractors, consolidator, tools |
| `goals/` | `GoalStore` (postgres.py), `GoalPlanner`, `GoalExecutor`, types, suggestion store |
| `workflow/` | `WorkflowStore`, `WorkflowPlanner`, `WorkflowScheduler`, types |
| `agents/research/` | `ResearchAgent` — web search and synthesis |
| `agents/companion/` | `CompanionAgent` — reasoning and conversation |
| `agents/goals/` | `GoalAgent` — conversational goal lifecycle |
| `agents/workflow/` | `WorkflowManagerAgent` — conversational workflow management |
| `jobs/` | Proactive jobs: briefing, insights, contact review, goal narrative/suggestion/stuck |
| `graph/workflow.py` | `build_workflow_graph()` — workflow execution graph |
| `graph/memory_hooks.py` | Post-memory-write hooks (e.g. contact extraction) |
| `plugin.py` | `PersonalPlugin(ZePlugin)` — wires all of the above into ze-core |

---

## ze-email — Email Domain

`ze_email` owns the Gmail channel and email agent. It depends on `ze-core`, `ze-google`,
and `ze-personal` (for contact extraction from email tool calls).

| Module | What it provides |
|--------|-----------------|
| `channel/gmail.py` | `GmailChannel` — Gmail API send/receive/poll |
| `agents/email/agent.py` | `EmailAgent` — inbox read, draft, send |
| `agents/email/tools.py` | Gmail `@tool` functions |
| `plugin.py` | `EmailPlugin(ZePlugin)` — registers agent when Google credentials are present |

---

## ze-prospecting — Prospecting Domain

`ze_prospecting` owns autonomous prospect research, campaign persistence, and stale
campaign recovery. It depends on `ze-core`, `ze-browser`, and `ze-personal`.

| Module | What it provides |
|--------|-----------------|
| `agents/agent.py` | `ProspectingAgent` — research + outreach drafting |
| `agents/tools.py` | `add_prospect`, `draft_outreach`, `log_outreach_event` tools |
| `store.py` | `ProspectCampaignStore` — campaign and outreach persistence |
| `jobs/campaigns.py` | `recover_stale_campaigns` — marks hung campaigns as failed |
| `plugin.py` | `ProspectingPlugin(ZePlugin)` — registers agent, store, and recovery job |

---

## ze-calendar — Calendar Domain

`ze_calendar` owns the calendar and reminders domain. It depends on `ze-core`,
`ze-google` (for credentials), and `ze-personal`.

| Module | What it provides |
|--------|-----------------|
| `agents/calendar/` | `CalendarAgent` — Google Calendar CRUD |
| `agents/reminders/` | `RemindersAgent` — NL time parsing, APScheduler firing |
| `reminders/store.py` | `ReminderStore` — reminder persistence |
| `reminders/calendar.py` | `CalendarReminderService` — Google Calendar sync and reminder scheduling |
| `reminders/calendar_store.py` | `CalendarReminderStore` — synced event persistence |
| `timezone/` | `TimezoneService`, `world_time` `@tool` |
| `jobs/calendar_reminder.py` | `CalendarReminderJob` — daily sync cron job |
| `plugin.py` | `CalendarPlugin(ZePlugin)` — registers agents and services |

---

## ze-google — Shared Google Credentials

`ze_google` provides a thin credential layer. It has no Ze dependencies and can be
imported by any package that needs Google OAuth2.

| Module | What it provides |
|--------|-----------------|
| `auth.py` | `GoogleCredentials`, `SCOPES`, service client factories |

---

## ze-news — News Package

`ze_news` owns news ingestion, personalised ranking, and credibility analysis.
Depends on `ze-core` only.

| Module | What it provides |
|--------|-----------------|
| `agents/news/` | `NewsAgent` — headlines and search tools |
| `jobs/fetch.py` | `NewsFetchJob` — RSS ingestion and embedding |
| `store.py` | `NewsStore` — article persistence + pgvector search |
| `registry.py` | `build_registry()` — source registry from config |
| `credibility.py` | LLM-based article credibility scoring |
| `personalization.py` | Interest-vector-based ranking |
| `plugin.py` | `NewsPlugin(ZePlugin)` — registers agent, conditionally loaded |

---

## ze-browser — Sidecar Client

`ze_browser` is a thin HTTP client for the browser sidecar service (Playwright + FastAPI
running as a separate process). It has no ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `client.py` | `BrowserClient` — `httpx`-based async client |
| `tool.py` | `@tool`-registered `browse_url` tool |
| `types.py` | `BrowserResult` |
| `errors.py` | `BrowserError` |

The sidecar itself is deployed separately and is never imported by any Python package.

---

## ze-notifications — Push Notifications

`ze_notifications` provides a transport-agnostic push notification abstraction.
No ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `notifier.py` | `Notifier` ABC |
| `ntfy.py` | `NtfyNotifier`, `NtfyConfig` — ntfy.sh/self-hosted ntfy implementation |
| `types.py` | `Notification` |

---

## ze-components — Server-Driven UI

`ze_components` defines server-driven UI component descriptors sent to the Flutter app
inside message frames. No ze dependencies.

| Module | What it provides |
|--------|-----------------|
| `types.py` | Component descriptor dataclasses |
| `tools.py` | `@tool`-registered render helpers (imported at startup for side effects) |

---

## ze-api — Application Shell

`ze_api` is the runnable deployment unit. It contains **no domain agents or jobs** —
only wiring, transport, and configuration. It depends on all Ze packages and registers
their `ZePlugin` implementations.

| Module | What it provides |
|--------|-----------------|
| `bootstrap.py` | `bootstrap_agents()` — DI resolution via plugin `agent_module_paths()` |
| `api/` | FastAPI app, WebSocket endpoint (`/ws`), REST routes, message route |
| `interface/native.py` | `NativeAppInterface` — WebSocket + ntfy delivery |
| `hooks.py` | `ToolCallCapHook` — per-turn tool call cap enforcement |
| `hooks/component_collection.py` | `ComponentCollectionHook` — collects UI components from agent results |
| `hooks/cost_cap.py` | `ToolCallCapHook` — per-turn tool call cap enforcement |
| `container.py` | `ZeContainer` — subclasses `ze_core.Container`, registers all plugins |
| `settings.py` | Pydantic `BaseSettings`, `to_core_settings()` bridge |

---

## ze-app — Flutter Client

`ze_app` is the native Flutter application for iOS, Android, macOS, and web. It
communicates with `ze-api` via WebSocket at `/ws`. It has no Python dependencies.

---

## The ZePlugin Extension Point

`ZePlugin` is the seam that lets domain packages inject behaviour into `ze-core`
without `ze-core` knowing about it.

```python
class ZePlugin(ABC):
    # Container-level hooks
    def agents(self) -> list[type[BaseAgent]]: ...
    def jobs(self) -> list[ProactiveJob]: ...
    def migrations_path(self) -> Path | None: ...

    # Graph-level hooks (applied at build time)
    def state_extensions(self) -> type | None: ...
    def graph_nodes(self) -> dict[str, Callable]: ...
    def graph_edges(self, builder: StateGraph) -> None: ...
    def configurable_services(self) -> dict[str, Any]: ...
    def agent_module_paths(self) -> list[str]: ...

    # Graph node hooks
    def register_proactive_jobs(self, scheduler, settings, *, consolidation_enabled=True): ...
```

Five plugins are registered in `ze_api/container.py`:

- **`PersonalPlugin`** (`ze_personal/plugin.py`) — identity builder, contact extraction
  hooks, goal-aware routing via `pre_route_node`, research/companion/goals/workflow agents,
  and proactive jobs (briefing, insights, contact review, goal narrative/suggestion/stuck).
- **`EmailPlugin`** (`ze_email/plugin.py`) — Gmail channel + email agent (when Google
  credentials are configured).
- **`ProspectingPlugin`** (`ze_prospecting/plugin.py`) — prospecting agent, campaign store,
  stale campaign recovery job.
- **`CalendarPlugin`** (`ze_calendar/plugin.py`) — calendar and reminders agent paths.
- **`NewsPlugin`** (`ze_news/plugin.py`) — conditionally loaded when `news.enabled: true`
  and sources are configured.

### Adding a new plugin

1. Create a class that inherits `ZePlugin` in your package.
2. Override only the methods you need (all have no-op defaults).
3. Instantiate it in `ze_api/container.py` and pass it to `build_graph()`:

```python
from ze_personal.plugin import PersonalPlugin
from ze_calendar.plugin import CalendarPlugin
from mypackage.plugin import MyPlugin

plugins = [PersonalPlugin(), CalendarPlugin(), MyPlugin()]
graph = build_graph(checkpointer=checkpointer, plugins=plugins)
bootstrap_agents(..., plugins=plugins)
```

Plugins are applied in order. State extension fields and graph nodes from all plugins
are merged before the graph is compiled.

---

## Where does new code go?

| New code | Package |
|----------|---------|
| New infrastructure primitive (router, gate, store type) | `ze-core` |
| New memory layer or retrieval policy | `ze-memory` |
| New domain concept tied to personal assistant | `ze-personal` |
| New Google integration credential | `ze-google` |
| New agent (general assistant: research, companion) | `ze-personal` → `ze_personal/agents/<name>/` |
| New agent (email) | `ze-email` → `ze_email/agents/<name>/` |
| New agent (prospecting) | `ze-prospecting` → `ze_prospecting/agents/` |
| New agent that needs calendar/reminder state | `ze-calendar` → `ze_calendar/agents/<name>/` |
| New agent that needs domain state (goals, workflows) | `ze-personal` → `ze_personal/agents/<name>/` |
| New background job (personal assistant domain) | `ze-personal` → `ze_personal/jobs/` + `PersonalPlugin.register_proactive_jobs()` |
| New background job (prospecting) | `ze-prospecting` → `ze_prospecting/jobs/` + `ProspectingPlugin.register_proactive_jobs()` |
| New channel implementation (LinkedIn, WhatsApp) | New package or existing domain package → `channel/` module |
| New push notification backend | `ze-notifications` |
| New server-driven UI component | `ze-components` |
| Headless browser interaction | `ze-browser` |

When in doubt: ask whether the code has a runtime dependency on `ze-personal` or
application config. If yes, it belongs in `ze-api`. If it depends only on `ze-core`
abstractions, it can live in `ze-personal`.

---

## When to create a new package

Most features do not need a new package. The default answer is **no** — add code to
an existing package. A new package earns its existence only when it satisfies specific
criteria.

### Signals that a new package is warranted

**Independent deployment boundary.** The code must be deployable, testable, or
replaceable in isolation from the rest of Ze. `ze-browser` exists because the
Playwright sidecar runs as a separate process — the client needs no Ze knowledge.
`ze-notifications` exists because the push transport may be swapped (ntfy today,
APNs tomorrow) without touching any domain code.

**Zero or very narrow upward dependencies.** A package that depends on everything
can never be extracted cleanly. The new package should sit at a natural layer
boundary with a clear, minimal import surface. If you find yourself importing from
`ze-api` or `ze-personal` inside the new package, it probably belongs in one of them
instead.

**A coherent, named domain.** `ze-calendar` exists because calendar + reminders is
a recognisable product subsystem with its own agents, store, jobs, and Google API
surface. `ze-memory` exists because memory is a foundational concern that multiple
packages depend on and that has its own migration history, types, and retrieval
semantics. "I have five new files" is not a domain.

**A `ZePlugin` implementation makes sense.** If the new subsystem contributes agents,
graph nodes, configurable services, or proactive jobs — and those contributions should
be togglable without touching `ze-core` or `ze-personal` — a plugin is the right
contract. If the subsystem does not need any of those seams, it probably should not
be a plugin-backed package.

### Signals that code belongs in an existing package

- It is a new agent that uses existing domain services (goals, workflows, contacts).
  → the relevant domain package (`ze-personal`, `ze-email`, etc.).
- It is a new proactive job tied to personal assistant domain logic.
  → `ze_personal/jobs/` + `PersonalPlugin.register_proactive_jobs()`.
- It is a new memory retrieval policy or graph predicate.
  → `ze-memory`.
- It is a new domain concept that belongs alongside existing personal assistant logic.
  → `ze-personal`.
- It is "calendar-adjacent" — it uses `GoogleCredentials` or calendar stores.
  → `ze-calendar`.

### The subsystem model

Ze thinks of each non-core package as a **subsystem**: a self-contained slice of
functionality with its own agents, stores, jobs, and migration path, stitched into
the graph through `ZePlugin`.

A subsystem should be able to answer "yes" to all three of these:

1. **Does it have its own Postgres tables?** (its own `migrations/versions/`)
2. **Does it contribute at least one agent or job?** (registered via plugin)
3. **Could you disable it** (`enabled: false` in config or by not registering the
   plugin) **without breaking the rest of Ze?**

If the answer to any of these is "no", the code is not a subsystem — it is a feature
that belongs inside an existing package.

### Practical checklist before creating a new package

- [ ] The new package has a name that describes a coherent domain, not an implementation detail.
- [ ] It does not import from `ze-api`, `ze-personal`, or any package above it in the dependency graph.
- [ ] It owns at least one Postgres migration.
- [ ] It has a `plugin.py` implementing `ZePlugin` (unless it is a pure library like `ze-google` or `ze-browser`).
- [ ] Adding or removing the plugin from `ze_api/container.py` requires no other code changes.
- [ ] It has its own `pyproject.toml` and `tests/` directory.
- [ ] A spec in `specs/phases/` or `specs/arch/` exists before any code is written.
