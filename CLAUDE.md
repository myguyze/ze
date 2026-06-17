# Ze — Claude Code Guide

## What this is

Ze is a single-user personal AI assistant. A Python/FastAPI backend with a LangGraph
orchestration layer routes user messages to specialised agents (research, companion,
calendar, email, workflow). Users interact via a React web app over WebSocket.
Push notifications are delivered via ntfy. All LLM calls go through OpenRouter.

## Repository layout

```
ze/                           # monorepo root
├── core/                     # Shared infrastructure — no domain knowledge
│   ├── ze-core/              # Engine — routing, orchestration, telemetry, DI container
│   │   └── ze_core/
│   │       ├── capability/   # CapabilityGate, PostgresCapabilityOverrideStore, modes
│   │       ├── openrouter/   # OpenRouterClient (engine internal — use LLMClient Protocol in plugins)
│   │       ├── orchestration/# graph_builder, graph nodes, AgentState, edges
│   │       ├── routing/      # EmbeddingRouter, ComplexityEstimator, fallback, store
│   │       ├── telemetry/    # CostTracker, CostReconciler, PostgresCostStore, ContextVar
│   │       ├── container.py  # Base Container with DI wiring and invoke/resume entry points
│   │       └── embeddings.py # Shared paraphrase-multilingual-MiniLM-L12-v2 singleton
│   ├── ze-agents/            # Developer API — BaseAgent, @agent, @tool, ZePlugin, shared types
│   │   └── ze_agents/
│   │       ├── channels/     # Channel ABC, ChannelRegistry, types
│   │       ├── interface/    # AppInterface ABC, InputPreprocessor, validation, types
│   │       ├── progress/     # ProgressReporter, translations
│   │       ├── base_agent.py # BaseAgent ABC with agentic_loop
│   │       ├── client.py     # LLMClient Protocol
│   │       ├── db.py         # DBPool Protocol
│   │       ├── errors.py     # Full ZeError hierarchy
│   │       ├── hooks.py      # HarnessHook ABC
│   │       ├── plugin.py     # ZePlugin ABC
│   │       ├── registry.py   # @agent decorator + AgentRegistry
│   │       ├── settings.py   # Settings dataclass
│   │       └── tool.py       # @tool decorator, ToolAccess
│   ├── ze-proactive/         # Job scheduling framework
│   │   └── ze_proactive/     # ProactiveJob, ProactiveScheduler, ProactiveNotifier, PushLogStore
│   ├── ze-sdk/               # Public SDK surface — flat re-export layer for plugin authors
│   │   └── ze_sdk/           # ze_sdk, ze_sdk.types, ze_sdk.proactive, ze_sdk.channels,
│   │                         # ze_sdk.memory, ze_sdk.errors
│   ├── ze-memory/            # Memory — facts, episodes, graph, retrieval
│   ├── ze-browser/           # Browser sidecar client (BrowserClient + tool)
│   ├── ze-notifications/     # Push notification abstraction (ntfy)
│   ├── ze-components/        # Server-driven UI component descriptors
│   └── ze-eval/              # Eval infrastructure — runner, judge, verifier, MCP server
├── plugins/                  # ZePlugin domain extensions
│   ├── ze-personal/          # Personal-assistant domain layer (ZePlugin)
│   │   └── ze_personal/
│   │       ├── contacts/     # PersonStore, ContactChannelStore, consolidator, extractors, tools
│   │       ├── goals/        # GoalStore, GoalPlanner, GoalExecutor, types
│   │       ├── graph/        # workflow.py (execution nodes), memory_hooks.py (contact extraction)
│   │       ├── persona/      # PostgresPersonaStore, identity builder, types
│   │       ├── agents/       # research, companion, goals, workflow agents
│   │       ├── jobs/         # briefing, insights, contacts, goal proactive jobs
│   │       ├── workflow/     # WorkflowStore, planner, scheduler, types
│   │       └── plugin.py     # PersonalPlugin(ZePlugin) — wires domain services into graphs
│   ├── ze-email/             # Gmail channel + email agent (ZePlugin)
│   │   └── ze_email/
│   │       ├── channel/      # GmailChannel
│   │       ├── agents/email/ # EmailAgent + tools
│   │       └── plugin.py     # EmailPlugin(ZePlugin)
│   ├── ze-calendar/          # Calendar, reminders, and timezone domain (ZePlugin)
│   │   └── ze_calendar/
│   │       ├── agents/       # CalendarAgent, RemindersAgent + tools
│   │       ├── reminders/    # ReminderStore, CalendarReminderService, CalendarReminderStore
│   │       ├── jobs/         # CalendarReminderJob
│   │       ├── timezone/     # TimezoneService, world_time @tool
│   │       └── plugin.py     # CalendarPlugin(ZePlugin) — registers agents
│   ├── ze-prospecting/       # Prospecting agent, campaign store, recovery job (ZePlugin)
│   │   └── ze_prospecting/
│   │       ├── agents/       # ProspectingAgent + tools
│   │       ├── jobs/         # recover_stale_campaigns
│   │       ├── store.py      # ProspectCampaignStore
│   │       └── plugin.py     # ProspectingPlugin(ZePlugin)
│   ├── ze-news/              # News fetching, RSS sources, NewsAgent, NewsPlugin
│   ├── ze-finance/           # Finance domain (ZePlugin) — in progress
│   └── ze-legal/             # Legal domain (ZePlugin) — in progress
├── integrations/             # External service wrappers — no Ze domain knowledge
│   └── ze-google/            # Google OAuth2 credentials and service client factories
├── apps/                     # Deployment units
│   ├── ze-api/               # HTTP/WebSocket API, wires all plugins
│   │   ├── ze_api/
│   │   │   ├── api/          # FastAPI app, WebSocket endpoint, REST routes
│   │   │   ├── interface/    # NativeAppInterface (WebSocket + ntfy delivery)
│   │   │   ├── bootstrap.py  # Agent DI wiring via plugin.agent_module_paths()
│   │   │   ├── container.py  # ZeContainer (registers all ZePlugins)
│   │   │   └── settings.py   # Pydantic Settings
│   │   ├── config/
│   │   │   ├── config.yaml   # Models, contacts, proactive schedules (secrets in .env)
│   │   │   └── persona.yaml  # Persona profiles and dials
│   │   ├── migrations/       # Alembic SQL migrations
│   │   └── tests/
│   └── ze-web/               # React web client (Vite + TypeScript + Tailwind + shadcn/ui)
├── eval/                     # Eval test data and entrypoints (uses core/ze-eval)
│   ├── scenarios/            # YAML scenario definitions — edit these to add tests
│   ├── results/              # JSON run outputs (gitignored)
│   ├── run.py                # CLI: python eval/run.py [--judge] [--tag X] [report]
│   └── server.py             # MCP server: python eval/server.py
├── specs/                    # Design specs (zc-* ze-core, numbered ze modules)
├── docs/                     # architecture.md, configuration.md, …
└── Makefile                  # make test, make test-core, make dev, …
```

### Package dependency graph

```
ze-browser      (no ze deps)             core/
ze-agents       (no ze deps)             core/
ze-proactive  → ze-agents                core/
ze-notifications(no ze deps)             core/
ze-components   (no ze deps)             core/
ze-memory     → ze-agents                core/
ze-eval         (no ze deps — HTTP only) core/  ← eval infrastructure
ze-sdk        → ze-agents, ze-proactive, ze-memory         core/  ← plugin entry point
ze-core       → ze-agents                core/  ← engine; never a plugin dep
ze-google       (no ze deps)             integrations/
ze-personal   → ze-sdk                   plugins/
ze-email      → ze-sdk, ze-google, ze-personal             plugins/
ze-prospecting→ ze-sdk, ze-browser, ze-personal            plugins/
ze-calendar   → ze-sdk, ze-google, ze-personal             plugins/
ze-news       → ze-sdk                   plugins/
ze-api        → ze-core, ze-sdk, ze-personal, ze-email, ze-prospecting, ze-calendar,
                  ze-google, ze-browser, ze-news, ze-notifications, ze-components   apps/
ze-web          (React — connects to ze-api over WebSocket, no Python deps)         apps/
```

## Essential commands

```bash
make help            # full target list

# Setup
make install         # Python workspace deps (uv sync)
make web-install     # React web app deps (bun install)

# Database
make db-up           # start Postgres via Docker
make migrate         # apply migrations (requires db-up first)

# Development
make dev             # backend only — uvicorn --reload on :8000
make web             # React web app — bun dev on :5173
make dev-full        # backend + web app together; Ctrl-C stops both
make logs            # tail the server log file

# Testing
make test            # ze-api tests, fast (skips slow embedding tests)
make test-all        # all packages, including slow ones
make test-personal   # ze-personal tests only
make test-calendar   # ze-calendar tests only
make web-test        # React web app tests (vitest)

# Code quality
make lint            # ruff lint across all Python packages
make format          # ruff format + fix across all Python packages

# Evals
make dev-eval        # backend without background jobs (use before running evals)
make eval-server     # start MCP eval server (requires dev-eval running; see docs/eval.md)
```

## Stack decisions (do not relitigate without reading specs/)

| Layer | Choice | Reason |
|---|---|---|
| LLM gateway | OpenRouter only | Single billing, easy model swap |
| Web search | OpenRouter `openrouter:web_search` server tool | No separate search API key; LLM decides when to search; billed via OpenRouter credits |
| Embeddings | paraphrase-multilingual-MiniLM-L12-v2 local | No API cost, multilingual, 384-dim |
| Orchestration | LangGraph + AsyncPostgresSaver | Graph persistence survives restarts |
| DB driver | asyncpg (runtime), psycopg2 (Alembic CLI) | asyncpg has no sync mode |
| Config | Pydantic BaseSettings + YAML files | Secrets in .env, structure in YAML |
| Migrations | Alembic raw SQL, no ORM | Explicit schema control |
| Client interface | React + WebSocket | Browser-first SPA; Tauri desktop wrapper deferred |
| Push notifications | ntfy | Self-hostable, no vendor lock-in, deep-link support |

## Coding conventions

### Python

- **Types**: dataclasses for domain types, Pydantic only in `ze_api/api/schemas.py`.
  Never use Pydantic models inside domain modules — use `types.py` dataclasses.
- **File naming**: `types.py` everywhere (never `models.py` — avoids ORM confusion).
- **DI**: Constructor injection in all classes; FastAPI `Depends()` only in `ze_api/api/`.
  No module-level globals that hold mutable state (except the `lru_cache` singletons
  in `settings.py` and `embeddings.py`).
- **OpenAPI**: Every REST route must declare `response_model`, `summary`, and
  `description`; request/query params use Pydantic or annotated `Query`. See
  `specs/phases/07-api.md`.
- **Logging**: Always use `get_logger(__name__)`. Never use `print()` or stdlib
  `logging` directly.
- **Errors**: Raise from `ze_api/errors.py` or `ze_sdk/errors.py`. Never raise bare
  `Exception` or `ValueError` in domain code — always use a typed subclass of `ZeError`.
- **Async**: All I/O is async. Fire-and-forget tasks use `asyncio.create_task()`.
  Never `asyncio.run()` inside a running event loop.
- **Comments**: Default to none. Only add a comment when the *why* is non-obvious.
- **Imports**: Plugin code imports from `ze_sdk.*` (agent API, types, proactive, memory,
  channels, errors). Domain types from `ze_personal.*` (contacts, goals, workflow, persona).
  Calendar/reminder domain from `ze_calendar.*`. Google credentials from `ze_google.*`.
  Engine internals (`ze_core.*`) are for `ze_api/` and `ze_core/` only — never import
  `ze_core` from a plugin package.

### Testing

- Tests live in `tests/` mirroring `ze/` structure.
- `asyncio_mode = "auto"` — all async tests just work, no `@pytest.mark.asyncio`.
- No real DB in unit tests. Mock asyncpg pools with `AsyncMock`.
- No real OpenRouter calls. Mock `client.complete` and `client.stream`.
- Settings fixtures: copy real YAML files to `tmp_path`, construct `Settings` with
  `config_dir=tmp_path/config`. Never monkey-patch Pydantic internals.
- Embedder in tests: use `make_embedder(agent_vecs, prompt_vec)` pattern (dict-keyed,
  sorted alphabetically) to match production load order.
- Slow tests (embedding model): mark with `@pytest.mark.slow`, skipped by default via
  `-m 'not slow'` in `make test`. Run with `make test-all`.
- Per-package test targets: `make test-core`, `make test-personal`, `make test-prospecting`,
  `make test-email`, `make test-calendar`, `make test-news`.

### Native app interface

- The `NativeAppInterface` in `ze_api/interface/native.py` handles all outbound delivery:
  WebSocket frames when the client is connected, ntfy push notifications otherwise.
- The WebSocket endpoint lives at `/ws`. One connection at a time — a new connection
  displaces the previous one with close code `4000`.
- On connect, unread messages are replayed from `MessageStore` before new frames flow.
- Confirmation requests are sent as `{"type": "confirmation", ...}` frames; the client
  replies with `{"type": "confirm", "id": "...", "choice": "approve"|"deny"|"edit"}`.
- `ConnectionManager` is on `app.state.connection_manager`; never instantiate it outside the lifespan.

## Configuration files

### `.env` (create from `.env.example`, never commit)
```
OPENROUTER_API_KEY=sk-or-...
ZE_API_KEY=your-secret-key
DATABASE_URL=postgresql://ze:ze@localhost:5432/ze
DATABASE_URL_SYNC=postgresql+psycopg2://ze:ze@localhost:5432/ze
NTFY_BASE_URL=https://ntfy.sh
NTFY_TOPIC=ze-your-topic
NTFY_TOKEN=your-ntfy-token
PUBLIC_URL=https://ze.fly.dev
LOG_LEVEL=INFO
CONFIRM_TIMEOUT_SECONDS=900
```

### `config/config.yaml`
Structural config: model assignments, contacts consolidation settings, proactive
schedules. Agent config (description, model, intents) lives on
`@agent` class attributes in Python — not in YAML.

Hot-reloaded on SIGHUP without restart.

## Adding a new agent

1. Write a spec in `specs/phases/` first (use `specs/TEMPLATE.md`; see `specs/README.md` for the index).
2. Create the agent in the appropriate package — `ze_personal/agents/`, `ze_email/agents/`,
   `ze_prospecting/agents/`, or `ze_calendar/agents/` — decorate with `@agent` from
   `ze_sdk`, subclass `BaseAgent` from `ze_sdk`.
   Put `description`, `model`, `intents`, `tools`, and `timeout` as class
   attributes. Define `_AGENT_INSTRUCTIONS` at the top.
3. Add a `tools.py` alongside the agent if it needs Python tools. Use `@tool` from
   `ze_sdk`. Use `"openrouter:web_search"` in `tools` for web search —
   no Python tool needed.
4. Add the module paths to the package's `ZePlugin.agent_module_paths()` — tools module
   first, then the agent module. The bootstrapper imports these at startup to fire `@agent`
   and `@tool` registration. No other wiring needed.
5. Write tests in `tests/agents/<name>/`.

See `docs/adding-an-agent.md` for the full authoring guide.

## Adding a new plugin

1. Create a `ZePlugin` subclass in `<package>/plugin.py`.
2. Declare the plugin via an entry point in the package's `pyproject.toml`:
   ```toml
   [project.entry-points."ze.plugins"]
   ze_myplugin = "ze_myplugin.plugin:MyPlugin"
   ```
3. Add the package to `apps/ze-api/pyproject.toml` dependencies.
4. Override `startup(container)` and `shutdown()` for async lifecycle needs.
5. Implement `memory_policies()` and `checkpoint_serde_modules()` when the plugin
   adds agents or checkpointed domain types.

Plugin discovery, topological ordering, and graph hook merging are automatic.
Add types to `plugin_deps` in `ze_api/container.py` only when the plugin
constructor needs a shared service not already in the dep map (phase 47b).

## LangGraph graph flow

```
[voice/image] → transcribe/caption ─┐
[text]                               ├→ embed_route → (compound?) → decompose → fetch_context → capability_check
                                                                  ↘ fetch_context ↗
capability_check → execute_tool → (compound?) → synthesize → write_memory → END
                 → draft_response → await_confirmation → END  (graph pauses here)
                 → END (blocked)
```

- Graph state: `AgentState` in `ze_core/orchestration/state.py`.
- Dependencies injected via `config["configurable"]` at invocation time (not build time).
- No token streaming to the client — the graph runs to completion, then the full
  response is sent as a WebSocket frame via `NativeAppInterface`. `graph.ainvoke()` is used (not `astream_events`).
- Confirmation resume: `graph.ainvoke(None, config)` with same `thread_id`.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Routing, research + companion agents, orchestration, API | Done |
| 2 | Memory — contradiction detection, episode summarisation, semantic retrieval | Done |
| 3 | Calendar + email agents, Google OAuth2 | Done |
| 4 | Workflow agent, multi-step planning, Postgres-persisted scheduler | Done |
| 5 | Memory consolidation — dedup facts, expire stale, summarise episodes | Done |
| 6 | User profile — synthesise facts + episodes into a structured portrait | Done |
| 7 | Proactive Ze — morning briefing, workflow failure alerts, calendar reminders | Done |
| 8 | Insight engine — weekly synthesis of facts + episodes into actionable insights | Done |
| 9 | Cost telemetry — per-flow/agent token tracking, automatic cost reconciliation | Done |
| 10 | Multimodal input — voice transcription + image/vision support | Done |
| 11 | Persona profiles + dials — named profiles, TARS-style numeric dials | Done |
| 12 | Contacts — person tracking, extraction from email/calendar/conversation, confirmation flow | Done |
| 13 | Reminders agent — NL time parsing, APScheduler firing, startup replay | Done |
| 14 | Progress messages — per-agent status messages, locale keys, atomic delete | Done |
| 15 | Introspection commands — costs, memory, contacts | Done |
| 16 | Agentic tool loop — LLM-driven ReAct loop in `BaseAgent`, calendar + email migrated | Done |
| 17 | Prospecting agent — autonomous target research, browser sidecar, outreach drafting | Done |
| 18 | Communication channel abstraction — `Channel` ABC, `EmailChannel`, contact channel handles | Done |
| 19 | Goal Engine — autonomous multi-week goal execution, verification gates, milestone loop | Done |
| 20 | Package architecture reorg — ze_core pure infra, ze-personal domain layer, ZePlugin ABC | Done |
| 21 | Agent harness — hook points, step-level abort, multi-agent handoffs | Done |
| 22 | Harness adoption — tool-call cap hook, research delegation, cancel command | Done |
| 23 | Goal engine v2 — milestone context injection, execution traces, adaptive replanning, enriched gate narrative | Done |
| 24 | Goal collaboration — goal-aware routing, conversational steering, post-goal retrospective, weekly narrative job | Done |
| 25 | Proactive goal suggestions — weekly LLM-generated goal proposals | Done |
| 26 | Stuck goal detection — idle milestone/gate alerts, recovery actions | Done |
| 27 | Cross-goal output reuse — prior milestone summaries injected into planner and executor prompts | Done |
| 28 | Cross-goal learning promotion — generalizable facts extracted from goal learnings and promoted to user memory on completion | Done |
| 44 | Calendar package split — ze-google (credentials), ze-calendar (agents, reminders, timezone), ze renamed to ze-api | Done |
| 45 | Native app interface — React web client, WebSocket transport, ntfy push notifications, ze-notifications + ze-components packages | Done |
| 46 | Accountability layer — weekly narrative, cost anomaly detection, confirmation persistence + replay + ntfy + timeout, `/status` command | Done |
| 48 | Core split — ze-agents (developer API), ze-proactive (job framework) extracted from ze-core | Done |
| 49 | Ze SDK — `ze-sdk` flat re-export layer; plugins import from `ze_sdk.*`, no direct ze-core dep | Done |
| 52 | Session-grouped episode consolidation — group episodes by session before archiving, one LLM summary per session | Done |
| 54 | Progress messages — plugin-local locale files, `ProgressTranslations.build()`, reporter wired end-to-end, `typing` frame carries text, `news.fetching` key for refresh | Done |
| 57 | Correlation engine — `ze-correlation` package, `CorrelationEngine`, `PostgresHypothesisStore`, graph neighbourhood expansion, recall guarantee, signal pinning | Done |
| 60 | Cross-plugin signal contract — `SignalSource` protocol, `ZePlugin.signal_sources()` hook, `NewsSignalSource`, `CalendarSignalSource`, container collection + dedup | Done |
