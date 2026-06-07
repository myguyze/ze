# Ze — Claude Code Guide

## What this is

Ze is a single-user personal AI assistant. A Python/FastAPI backend with a LangGraph
orchestration layer routes user messages to specialised agents (research, companion,
calendar, email, workflow). Users interact via a Telegram bot. All LLM calls go through
OpenRouter.

## Repository layout

```
ze/                           # monorepo root
├── packages/
│   ├── ze-core/              # Pure infrastructure — routing, memory, orchestration, telemetry, …
│   │   └── ze_core/
│   │       ├── capability/   # CapabilityGate, PostgresCapabilityOverrideStore, modes
│   │       ├── channels/     # Channel ABC, ChannelRegistry, types
│   │       ├── interface/    # AppInterface ABC, InputPreprocessor, validation, types
│   │       ├── memory/       # PostgresMemoryStore, consolidator, extractor, types
│   │       ├── openrouter/   # OpenRouterClient, types
│   │       ├── orchestration/# graph_builder, BaseAgent, @agent, @tool, registry, nodes, state
│   │       ├── plugin.py     # ZePlugin ABC (container + graph extension seam)
│   │       ├── proactive/    # ProactiveScheduler, ProactiveNotifier, ProactiveJob
│   │       ├── progress/     # ProgressReporter, translations
│   │       ├── routing/      # EmbeddingRouter, ComplexityEstimator, fallback, store
│   │       ├── telemetry/    # CostTracker, CostReconciler, PostgresCostStore, ContextVar
│   │       ├── container.py  # Base Container with DI wiring and invoke/resume entry points
│   │       └── embeddings.py # Shared paraphrase-multilingual-MiniLM-L12-v2 singleton
│   ├── ze-personal/          # Personal-assistant domain layer (ZePlugin)
│   │   └── ze_personal/
│   │       ├── contacts/     # PersonStore, ContactChannelStore, consolidator, extractors, tools
│   │       ├── goals/        # GoalStore, GoalPlanner, GoalExecutor, types
│   │       ├── graph/        # workflow.py (execution nodes), memory_hooks.py (contact extraction)
│   │       ├── persona/      # PostgresPersonaStore, identity builder, types
│   │       ├── workflow/     # WorkflowStore, planner, scheduler, types
│   │       └── plugin.py     # PersonalPlugin(ZePlugin) — wires domain services into graphs
│   ├── ze-google/            # Shared Google OAuth2 credentials (no Ze deps)
│   │   └── ze_google/
│   │       └── auth.py       # GoogleCredentials, SCOPES, service client factories
│   ├── ze-calendar/          # Calendar, reminders, and timezone domain (ZePlugin)
│   │   └── ze_calendar/
│   │       ├── agents/       # CalendarAgent, RemindersAgent + tools
│   │       ├── reminders/    # ReminderStore, CalendarReminderService, CalendarReminderStore
│   │       ├── jobs/         # CalendarReminderJob
│   │       ├── timezone/     # TimezoneService, world_time @tool
│   │       └── plugin.py     # CalendarPlugin(ZePlugin) — registers agents
│   ├── ze-api/               # Deployment unit — HTTP/WebSocket API, Telegram bot, wires all plugins
│   │   ├── ze_api/
│   │   │   ├── agents/       # email, companion, research, prospecting agents + bootstrap
│   │   │   ├── api/          # FastAPI app, WebSocket endpoint, REST routes
│   │   │   ├── google/       # GmailChannel (imports GoogleCredentials from ze_google)
│   │   │   ├── jobs/         # Proactive cron jobs: briefing, insights, contacts, goal jobs
│   │   │   ├── container.py  # ZeContainer (registers PersonalPlugin + CalendarPlugin)
│   │   │   └── settings.py   # Pydantic Settings
│   │   ├── config/
│   │   │   ├── config.yaml   # Models, contacts, proactive schedules (secrets in .env)
│   │   │   └── persona.yaml  # Persona profiles and dials
│   │   ├── migrations/       # Alembic SQL migrations
│   │   └── tests/
│   └── ze-browser/           # Browser sidecar client (BrowserClient + tool)
├── specs/                    # Design specs (zc-* ze-core, numbered ze modules)
├── docs/                     # architecture.md, configuration.md, …
└── Makefile                  # make test, make test-core, make dev-poll, …
```

### Package dependency graph

```
ze-browser    (no ze deps)
ze-core       (no ze deps)
ze-personal → ze-core
ze-google     (no ze deps)
ze-calendar → ze-core, ze-google, ze-personal
ze-api      → ze-core, ze-personal, ze-calendar, ze-google, ze-browser, ze-news, ze-notifications, ze-components
```

## Essential commands

```bash
make help            # full target list
make db-up           # start Postgres via Docker
make migrate         # apply migrations (requires db-up first)
make dev-poll        # Telegram long-polling — interact via Telegram locally (primary dev mode)
make dev             # uvicorn --reload on :8000 — REST API only, no Telegram
make test            # tests, fast (skips embedding model load)
make test-all        # all tests including slow ones
make dev-eval        # start REST API without Telegram webhook (use this before running evals)
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
| Bot interface | aiogram 3.x (Telegram) | Async-native, no separate frontend to maintain |

## Coding conventions

### Python

- **Types**: dataclasses for domain types, Pydantic only in `ze/api/schemas.py`.
  Never use Pydantic models inside domain modules — use `types.py` dataclasses.
- **File naming**: `types.py` everywhere (never `models.py` — avoids ORM confusion).
- **DI**: Constructor injection in all classes; FastAPI `Depends()` only in `ze/api/`.
  No module-level globals that hold mutable state (except the `lru_cache` singletons
  in `settings.py` and `embeddings.py`).
- **OpenAPI**: Every REST route must declare `response_model`, `summary`, and
  `description`; request/query params use Pydantic or annotated `Query`. See
  `specs/phases/07-api.md`.
- **Logging**: Always use `get_logger(__name__)`. Never use `print()` or stdlib
  `logging` directly. Bind `chat_id` at webhook request time via `bind_context()`.
- **Errors**: Raise from `ze/errors.py`. Never raise bare `Exception` or `ValueError`
  in domain code — always use a typed subclass of `ZeError`.
- **Async**: All I/O is async. Fire-and-forget tasks use `asyncio.create_task()`.
  Never `asyncio.run()` inside a running event loop.
- **Comments**: Default to none. Only add a comment when the *why* is non-obvious.
- **Imports**: Infrastructure types from `ze_core.*` (orchestration, routing, memory,
  telemetry). Domain types from `ze_personal.*` (contacts, goals, workflow, persona).
  Calendar/reminder domain from `ze_calendar.*`. Google credentials from `ze_google.*`.
  Ze-specific behaviour (Telegram, API, jobs) stays in `ze_api/`.

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
  `make test`. Run with `make test-all`.

### Telegram bot

- All bot logic lives in `ze/telegram/`. The FastAPI router (`ze/api/telegram.py`)
  handles HTTP only; it delegates to `ZeBot` for all bot-level behaviour.
- `ZeBot` is constructed in the lifespan and stored on `app.state.bot`. Never
  instantiate it outside the lifespan.
- Inline keyboard payloads use the `confirm:<decision>` format. Keep payloads
  under 64 bytes (Telegram callback data limit).
- ForceReply state is tracked in `ActiveSessionStore` alongside active graph
  invocations. Clear it on any terminal state (done, expired, error).

## Configuration files

### `.env` (create from `.env.example`, never commit)
```
OPENROUTER_API_KEY=sk-or-...
ZE_API_KEY=your-secret-key
DATABASE_URL=postgresql://ze:ze@localhost:5432/ze
DATABASE_URL_SYNC=postgresql+psycopg2://ze:ze@localhost:5432/ze
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_WEBHOOK_SECRET=your-webhook-secret
TELEGRAM_ALLOWED_CHAT_ID=your-telegram-chat-id
PUBLIC_URL=https://ze.fly.dev
LOG_LEVEL=INFO
CONFIRM_TIMEOUT_SECONDS=900
```

### `config/config.yaml`
Structural config: model assignments, contacts consolidation settings, proactive
schedules. Agent config (description, model, capabilities, intent_map) lives on
`@agent` class attributes in Python — not in YAML.

Hot-reloaded on SIGHUP without restart.

## Adding a new agent

1. Write a spec in `specs/phases/` first (use `specs/TEMPLATE.md`; see `specs/README.md` for the index).
2. Create `ze_api/agents/<name>/agent.py` — decorate with `@agent` from `ze_core.orchestration.registry`, subclass `BaseAgent` from `ze_core.orchestration.base_agent`. Put `description`, `model`, `capabilities`, `intent_map`, `tools`, and `timeout` as class attributes. Define `_AGENT_INSTRUCTIONS` at the top.
3. Add `ze_api/agents/<name>/tools.py` if the agent needs Python tools. Use `@tool` from `ze_core.orchestration.tool`. Use `"openrouter:web_search"` in `tools` for web search — no Python tool needed.
4. Write tests in `tests/agents/<name>/`.
5. Wire the live instance in `ze_api/container.py` via `register_instance()`.
6. Import the tools module at startup so `@tool` registration fires.

See `docs/adding-an-agent.md` for the full authoring guide.

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
  response is sent via the Telegram Bot API. `graph.ainvoke()` is used (not `astream_events`).
- Confirmation resume: `graph.ainvoke(None, config)` with same `thread_id`.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Routing, research + companion agents, orchestration, API, Telegram bot | Done |
| 2 | Memory — contradiction detection, episode summarisation, semantic retrieval | Done |
| 3 | Calendar + email agents, Google OAuth2 | Done |
| 4 | Workflow agent, multi-step planning, Postgres-persisted scheduler | Done |
| 5 | Memory consolidation — dedup facts, expire stale, summarise episodes | Done |
| 6 | User profile — synthesise facts + episodes into a structured portrait | Done |
| 7 | Proactive Ze — morning briefing, workflow failure alerts, calendar reminders | Done |
| 8 | Insight engine — weekly synthesis of facts + episodes into actionable insights | Done |
| 9 | Cost telemetry — per-flow/agent token tracking, automatic cost reconciliation | Done |
| 10 | Multimodal input — voice transcription + image/vision support | Done |
| 11 | Persona profiles + dials — named profiles, TARS-style numeric dials, `/persona` command | Done |
| 12 | Contacts — person tracking, extraction from email/calendar/conversation, confirmation flow | Done |
| 13 | Reminders agent — NL time parsing, APScheduler firing, startup replay | Done |
| 14 | Progress messages — per-agent Telegram status messages, locale keys, atomic delete | Done |
| 15 | Telegram commands — `/costs`, `/memory`, `/contacts` introspection commands | Done |
| 16 | Agentic tool loop — LLM-driven ReAct loop in `BaseAgent`, calendar + email migrated | Done |
| 17 | Prospecting agent — autonomous target research, browser sidecar, outreach drafting | Done |
| 18 | Communication channel abstraction — `Channel` ABC, `EmailChannel`, contact channel handles | Done |
| 19 | Goal Engine — autonomous multi-week goal execution, verification gates, milestone loop | Done |
| 20 | Package architecture reorg — ze_core pure infra, ze-personal domain layer, ZePlugin ABC | Done |
| 21 | Agent harness — hook points, step-level abort, multi-agent handoffs | Done |
| 22 | Harness adoption — tool-call cap hook, research delegation, `/cancel` command | Done |
| 23 | Goal engine v2 — milestone context injection, execution traces, adaptive replanning, enriched gate narrative | Done |
| 24 | Goal collaboration — goal-aware routing, conversational steering, post-goal retrospective, weekly narrative job | Done |
| 25 | Proactive goal suggestions — weekly LLM-generated goal proposals via Telegram | Done |
| 26 | Stuck goal detection — idle milestone/gate alerts, Telegram recovery actions | Done |
| 27 | Cross-goal output reuse — prior milestone summaries injected into planner and executor prompts | Done |
| 28 | Cross-goal learning promotion — generalizable facts extracted from goal learnings and promoted to user memory on completion | Done |
| 44 | Calendar package split — ze-google (credentials), ze-calendar (agents, reminders, timezone), ze renamed to ze-api | Done |
