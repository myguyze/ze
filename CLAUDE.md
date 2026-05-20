# Ze — Claude Code Guide

## What this is

Ze is a single-user personal AI assistant. A Python/FastAPI backend with a LangGraph
orchestration layer routes user messages to specialised agents (research, companion,
calendar, email, workflow). Users interact via a Telegram bot. All LLM calls go through
OpenRouter.

## Repository layout

```
ze/
├── ze/                       # Python package
│   ├── api/                  # FastAPI app, Telegram webhook handler, REST routes
│   ├── agents/               # BaseAgent ABC, registry, research + companion agents
│   ├── capability/           # CapabilityGate — permission enforcement
│   ├── memory/               # MemoryStore (Phase 1 stub), UserFact, Episode types
│   ├── openrouter/           # OpenRouterClient (complete() + stream())
│   ├── orchestration/        # LangGraph state machine (nodes/, edges, graph, state)
│   ├── routing/              # EmbeddingRouter + haiku_fallback
│   ├── telegram/             # ZeBot, keyboards, session store
│   ├── container.py          # Dependency wiring — builds all shared resources
│   ├── db.py                 # asyncpg pool factory
│   ├── embeddings.py         # SentenceTransformer singleton
│   ├── errors.py             # Ze exception hierarchy
│   ├── logging.py            # structlog JSON config
│   └── settings.py           # Pydantic BaseSettings (single config source)
├── config/
│   ├── agents/               # One YAML per agent (description, model, tools, timeout)
│   ├── capabilities.yaml     # Per-agent permission modes
│   └── models.yaml           # Model names + routing thresholds
├── migrations/versions/      # Alembic raw-SQL migrations (no ORM)
│   ├── 001_initial_schema.py # routing_log, user_facts, episodes
│   └── 002_checkpointer.py   # LangGraph checkpoint tables
├── tests/                    # Mirrors ze/ structure
├── specs/                    # All 8 design specs (read before modifying a module)
├── Dockerfile                # Production image
├── docker-compose.yml        # Postgres (pgvector/pgvector:pg16) + backend
├── fly.toml                  # Fly.io deployment config
├── pyproject.toml            # Python project + dependencies
└── Makefile                  # All dev commands (see `make help`)
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
```

## Stack decisions (do not relitigate without reading specs/)

| Layer | Choice | Reason |
|---|---|---|
| LLM gateway | OpenRouter only | Single billing, easy model swap |
| Embeddings | all-MiniLM-L6-v2 local | No API cost, fast, 384-dim |
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
  `specs/07-api.md`.
- **Logging**: Always use `get_logger(__name__)`. Never use `print()` or stdlib
  `logging` directly. Bind `chat_id` at webhook request time via `bind_context()`.
- **Errors**: Raise from `ze/errors.py`. Never raise bare `Exception` or `ValueError`
  in domain code — always use a typed subclass of `ZeError`.
- **Async**: All I/O is async. Fire-and-forget tasks use `asyncio.create_task()`.
  Never `asyncio.run()` inside a running event loop.
- **Comments**: Default to none. Only add a comment when the *why* is non-obvious.

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
TAVILY_API_KEY=tvly-...
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

### `config/agents/<name>.yaml`
```yaml
enabled: true
description: "One sentence used for embedding-based routing."
model: anthropic/claude-sonnet-4-5
timeout: 30
intent_map:
  read: "Search and retrieve information."
```

### `config/capabilities.yaml`
Permission modes per `agent.intent`: `autonomous` | `confirm` | `draft_only` | `disabled`.
Hot-reloaded on SIGHUP without restart.

### `config/models.yaml`
Routing thresholds (`threshold`, `gap_threshold`) and model assignments.

## Adding a new agent

1. Write a spec in `specs/` first.
2. Add `config/agents/<name>.yaml` with `enabled: false` initially.
3. Add `config/capabilities.yaml` entry.
4. Create `ze/agents/<name>/agent.py` — subclass `BaseAgent`, add `@register`.
5. Add `ze/agents/<name>/tools.py`. Define `_AGENT_INSTRUCTIONS` at the top of `agent.py`.
6. Write tests in `tests/agents/<name>/`.
7. Register the live instance in `ze/api/app.py` lifespan via `register_instance()`.
8. Set `enabled: true` in the agent YAML when ready.

## LangGraph graph flow

```
embed_route → (compound?) → decompose → fetch_context → capability_check
                                     ↘ fetch_context ↗
capability_check → execute_tool → (compound?) → synthesize → write_memory → END
                 → draft_response → await_confirmation → END  (graph pauses here)
                 → END (blocked)
```

- Graph state: `AgentState` in `ze/orchestration/state.py`.
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
| 5 | Memory consolidation — dedup facts, expire stale, summarise episodes | Not started |
