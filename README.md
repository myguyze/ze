# Ze — Personal AI Assistant

A single-user AI assistant that routes conversations to specialised agents (research,
companion, calendar, email) via a LangGraph orchestration layer. Communicates over
WebSocket with a Next.js frontend. All LLM inference goes through OpenRouter.

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · LangGraph |
| LLM gateway | OpenRouter (all models) |
| Embeddings | `all-MiniLM-L6-v2` (local, no API cost) |
| Graph persistence | LangGraph `AsyncPostgresSaver` → Postgres |
| Database | PostgreSQL 16 + pgvector |
| Migrations | Alembic (raw SQL) |
| Frontend | Next.js 14 · React 18 · Tailwind CSS |
| Deployment | Fly.io |

## Prerequisites

- Python 3.12+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) — `pip install uv`
- Docker (for Postgres)

## Quick start

```bash
# 1. Clone
git clone <repo-url> ze && cd ze

# 2. Install dependencies
make install

# 3. Configure secrets
cp backend/.env.example backend/.env
# Edit backend/.env — fill in OPENROUTER_API_KEY, TAVILY_API_KEY, ZE_API_KEY

# 4. Start Postgres and apply migrations
make db-up
make migrate

# 5. Start the backend and frontend
make dev-be   # terminal 1 — http://localhost:8000
make dev-fe   # terminal 2 — http://localhost:3000
```

## Environment variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key |
| `TAVILY_API_KEY` | Yes | Tavily search API key (research agent) |
| `ZE_API_KEY` | Yes | Static bearer token for WebSocket auth |
| `DATABASE_URL` | No | asyncpg-format Postgres URL (default: `postgresql://ze:ze@localhost:5432/ze`) |
| `DATABASE_URL_SYNC` | No | psycopg2-format URL for Alembic CLI |
| `CORS_ORIGINS` | No | Comma-separated allowed origins (default: `http://localhost:3000`) |
| `CONFIRM_TIMEOUT_SECONDS` | No | Confirmation timeout in seconds (default: `900`) |
| `LOG_LEVEL` | No | `DEBUG` / `INFO` / `WARNING` (default: `INFO`) |

## Development commands

```bash
make help           # list all targets

make test           # backend unit tests (fast)
make test-all       # include slow embedding-model tests
make test-fe        # frontend typecheck + lint

make lint           # ruff (backend) + eslint (frontend)
make migrate        # apply pending DB migrations
make migrate-down   # roll back one step
make db-reset       # drop + recreate the database
```

## Project structure

```
ze/
├── backend/
│   ├── ze/
│   │   ├── api/          # FastAPI app, WebSocket handler, REST routes
│   │   ├── agents/       # Agent implementations (research, companion, …)
│   │   ├── capability/   # Permission gate (autonomous / confirm / draft_only)
│   │   ├── memory/       # User facts + episodic memory (Phase 2)
│   │   ├── openrouter/   # LLM client (complete + stream)
│   │   ├── orchestration/# LangGraph graph, nodes, edges, state
│   │   └── routing/      # Embedding router + Haiku fallback
│   ├── config/
│   │   ├── agents/       # Per-agent YAML (model, tools, timeout, description)
│   │   ├── capabilities.yaml
│   │   └── models.yaml
│   └── migrations/       # Alembic versions
├── frontend/
│   ├── app/              # Next.js App Router
│   ├── components/       # React components
│   ├── hooks/            # useZeSocket, etc.
│   └── types/            # Shared TS types (mirrors backend schemas)
└── specs/                # Design specs for every module
```

## Agent routing

Incoming messages are scored against agent embeddings (cosine similarity). If the
top score is above threshold and the gap to the second agent is wide enough, the
message routes directly. Otherwise Haiku decomposes it into subtasks — one per agent.

```
User message
  → EmbeddingRouter (all-MiniLM-L6-v2, local)
      confident → agent directly
      ambiguous → Haiku decompose → one or more agents
  → CapabilityGate (autonomous / confirm / draft_only / blocked)
  → Agent.run() with asyncio.wait_for timeout
  → memory written (fire and forget)
  → response streamed token by token over WebSocket
```

## Agents

| Agent | Phase | Description |
|---|---|---|
| `research` | 1 ✅ | Web search via Tavily + OpenRouter synthesis |
| `companion` | 1 ✅ | Conversational reasoning, memory injection |
| `calendar` | 3 | Google Calendar read/write |
| `email` | 3 | Gmail read/draft/send |
| `workflow` | 4 | Multi-step task planning and execution |

## Capability gate

Each `agent.intent` pair has a permission mode in `config/capabilities.yaml`:

- `autonomous` — executes immediately
- `confirm` — shows a draft and waits for user approval (15-min timeout)
- `draft_only` — generates draft, never executes without a YAML change
- `disabled` — always blocked

Session-scoped overrides can escalate within the YAML ceiling. Config hot-reloads on `SIGHUP`.

## Docker

```bash
make docker-up      # start all services (Postgres + backend + frontend)
make docker-down    # stop all services
make docker-build   # rebuild images
```

## Deployment (Fly.io)

```bash
fly deploy          # deploy backend
# frontend deployed separately (Vercel or second Fly app)
```

Set all env vars as Fly secrets: `fly secrets set OPENROUTER_API_KEY=...`