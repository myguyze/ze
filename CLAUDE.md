# Ze — Claude Code Guide

## What this is

Ze is a single-user personal AI assistant. A Python/FastAPI backend with a LangGraph
orchestration layer routes user messages to specialised agents (research, companion,
calendar, email, workflow). A Next.js 14 frontend communicates exclusively over
WebSocket. All LLM calls go through OpenRouter.

## Repository layout

```
ze/
├── backend/                  # Python package (uv)
│   ├── ze/
│   │   ├── api/              # FastAPI app, WebSocket handler, REST routes
│   │   ├── agents/           # BaseAgent ABC, registry, research + companion agents
│   │   ├── capability/       # CapabilityGate — permission enforcement
│   │   ├── memory/           # MemoryStore (Phase 1 stub), UserFact, Episode types
│   │   ├── openrouter/       # OpenRouterClient (complete() + stream())
│   │   ├── orchestration/    # LangGraph state machine (nodes/, edges, graph, state)
│   │   ├── routing/          # EmbeddingRouter + haiku_fallback
│   │   ├── db.py             # asyncpg pool factory
│   │   ├── embeddings.py     # SentenceTransformer singleton
│   │   ├── errors.py         # Ze exception hierarchy
│   │   ├── logging.py        # structlog JSON config
│   │   └── settings.py       # Pydantic BaseSettings (single config source)
│   ├── config/
│   │   ├── agents/           # One YAML per agent (description, model, tools, timeout)
│   │   ├── capabilities.yaml # Per-agent permission modes
│   │   └── models.yaml       # Model names + routing thresholds
│   ├── migrations/versions/  # Alembic raw-SQL migrations (no ORM)
│   │   ├── 001_initial_schema.py   # routing_log, user_facts, episodes
│   │   └── 002_checkpointer.py     # LangGraph checkpoint tables
│   └── tests/                # Mirrors ze/ structure
├── frontend/
│   ├── app/                  # Next.js 14 App Router (page.tsx = Server Component)
│   ├── components/           # React components (ChatClient is the 'use client' root)
│   ├── hooks/                # useZeSocket and other custom hooks
│   ├── lib/                  # env.ts (Zod validation), utils
│   └── types/                # Shared TypeScript types
├── specs/                    # All 9 design specs (read before modifying a module)
├── docker-compose.yml        # Postgres (pgvector/pgvector:pg16) + backend + frontend
├── fly.toml                  # Fly.io deployment config
└── Makefile                  # All dev commands (see `make help`)
```

## Essential commands

```bash
make help            # full target list
make db-up           # start Postgres via Docker
make migrate         # apply migrations (requires db-up first)
make dev-be          # uvicorn --reload on :8000
make dev-fe          # next dev on :3000
make test            # backend tests, fast (skips embedding model load)
make test-all        # all backend tests including slow ones
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
| Frontend | Next.js 14 App Router | Server Components + 'use client' boundary |
| Styling | Tailwind CSS | No component library |

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
  `logging` directly. Bind `session_id` at WebSocket connect time via `bind_context()`.
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

### Frontend

- `app/page.tsx` is a **Server Component** — no hooks, no browser APIs.
- `ChatClient.tsx` is the `'use client'` boundary — all interactivity lives here or below.
- Env vars validated at build time via `lib/env.ts` (Zod). Never access
  `process.env` directly in components.
- WS message types live in `types/index.ts` — keep in sync with `ze/api/schemas.py`.

## Configuration files

### `.env` (create from `.env.example`, never commit)
```
OPENROUTER_API_KEY=sk-or-...
TAVILY_API_KEY=tvly-...
ZE_API_KEY=your-secret-key
NEXT_PUBLIC_ZE_API_KEY=your-secret-key
DATABASE_URL=postgresql://ze:ze@localhost:5432/ze
DATABASE_URL_SYNC=postgresql+psycopg2://ze:ze@localhost:5432/ze
CORS_ORIGINS=http://localhost:3000
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
5. Add `ze/agents/<name>/prompt.py`, `tools.py`, `intent_map.py`.
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
- Token streaming: `execute_tool` puts tokens into an `asyncio.Queue` passed through
  `config["configurable"]["token_queue"]`. The WS handler consumes concurrently.
- Confirmation resume: `graph.ainvoke(None, config)` with same `thread_id`.

## Phase status

| Phase | Scope | Status |
|---|---|---|
| 1 | Routing, research + companion agents, orchestration, API, frontend | In progress |
| 2 | Memory (full implementation), contradiction detection, episode embeddings | Not started |
| 3 | Calendar + email agents, Google OAuth2 | Not started |
| 4 | Workflow agent, multi-step planning | Not started |
