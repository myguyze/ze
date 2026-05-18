# API — Spec

## Purpose

FastAPI application that exposes a Telegram webhook endpoint for chat, REST
endpoints for configuration and memory management, and owns session lifecycle.
It is the only entry point into Ze — all external communication goes through here.

## Responsibilities

- Accept Telegram webhook updates via `POST /telegram/webhook`.
- Authenticate webhook requests via Telegram's `X-Telegram-Bot-Api-Secret-Token` header.
- Authenticate REST requests via static API key (`ZE_API_KEY` bearer token).
- Dispatch incoming Telegram messages into the LangGraph orchestration graph.
- Send responses back via the Telegram Bot API (typing action while running, then full message).
- Handle confirmation flow via Telegram inline keyboards; resume paused graphs on callback.
- Expire paused graphs after `CONFIRM_TIMEOUT_SECONDS` (default 900).
- Expose REST endpoints for capabilities, memory, and routing log.
- Publish machine-readable OpenAPI documentation for all REST endpoints (see
  [OpenAPI documentation](#openapi-documentation)).
- Wire all dependencies via FastAPI `Depends()` in `dependencies.py`.
- Manage FastAPI lifespan: DB pool, embedding model, graph, checkpointer, aiogram Bot.

## Out of Scope

- Does not implement business logic — delegates to orchestration and domain modules.
- Does not serve a frontend (Telegram is the interface).
- Does not handle Google OAuth2 flows (Phase 3).
- WebSocket endpoint: not implemented. Reserved for a future Telegram Mini App phase.
  When that phase begins, add `WS /ws/{session_id}` alongside the Telegram webhook.

## Endpoints

### Telegram Webhook

```
POST /telegram/webhook
```

Authentication: Telegram sends an `X-Telegram-Bot-Api-Secret-Token` header on every
request. FastAPI verifies it against `TELEGRAM_WEBHOOK_SECRET` before processing.
Requests with a missing or invalid token return HTTP 401.

The webhook is registered at startup via the Bot API (`setWebhook`) pointing at
`https://<host>/telegram/webhook`. See `08-telegram.md` for the full bot spec.

**Inbound update types handled:**

| Type | Action |
|------|--------|
| `message` (text) | Dispatch to orchestration graph; session keyed by `chat_id`. |
| `callback_query` | Resume a paused confirmation graph; decision from the button payload. |

All other update types are acknowledged (HTTP 200) and ignored.

**Message flow:**

```
Telegram POSTs Update to /telegram/webhook
    → verify secret_token header
    → message.text  → graph.ainvoke(state, config={thread_id: str(chat_id)})
                    → sendChatAction("typing") while running
                    → send full response message on completion
                    → on interrupt: send ConfirmationRequest message with inline keyboard
    → callback_query → verify pending confirmation state
                     → graph.ainvoke(None, config)  # resume
                     → send full response on completion
```

Confirmation inline keyboard payload:

```python
# Button payloads sent in callback_query.data
"confirm:yes"
"confirm:no"
"confirm:edit"   # triggers ForceReply message asking for edited content
```

On `confirm:edit` the bot sends a ForceReply message. The user's reply to that
message is treated as a `ConfirmMessage(decision="edit", edit_content=<text>)`.

---

### REST Endpoints

#### Capabilities

```
GET  /capabilities
     → returns current capabilities.yaml as JSON

PUT  /capabilities/{agent}/{intent}
     Body: { "mode": "autonomous" | "confirm" | "draft_only" | "disabled" }
     → validates agent and intent are known, updates YAML atomically
     → returns updated config for that agent
```

#### Memory

```
GET  /memory/facts
     → returns all UserFact records (reviewed + unreviewed)

POST /memory/facts/review
     Body: { "actions": [{ "id": UUID, "action": "confirm" | "reject" | "edit", "value"?: str }] }
     → applies each action; sets reviewed=True on confirm, deletes on reject,
       updates value + sets reviewed=True on edit
     → returns updated list of affected facts

GET  /memory/digest
     → returns { unreviewed_facts, contradicted_facts, recent_episodes (last 10) }
```

#### Routing Log

```
GET  /routing/log?limit=50&offset=0
     → returns paginated routing_log rows, newest first
```

## Pydantic Schemas

All schemas live in `ze/api/schemas.py`. This is the only file that defines
Pydantic models. Domain dataclasses (in `types.py` files) are converted to
response schemas here before serialisation.

## OpenAPI documentation

FastAPI generates OpenAPI 3.1 automatically. Ze requires every REST route to
participate fully in that schema:

- **Response models**: declare `response_model` on every REST handler. Request
  bodies use Pydantic models in `schemas.py` (already required).
- **Route metadata**: each handler must set `summary` and `description` (what it
  does, not how it is implemented).
- **Tags**: routers use `tags=[...]` matching the `openapi_tags` list in
  `ze/api/app.py`.
- **Query parameters**: use `Query(..., description=...)` for documented
  pagination and filters.
- **Errors**: document non-validation error responses (e.g. HTTP 422 from
  unknown agent/intent) via the route `responses` dict where applicable.

Interactive docs are served at `GET /docs` (Swagger UI) and `GET /redoc`
(ReDoc) in development. WebSocket endpoints are excluded from OpenAPI (they are
documented in this spec and in `schemas.py` WS message types).

## Dependencies (FastAPI `Depends()`)

All factories live in `ze/api/dependencies.py`.

```python
async def get_settings() -> Settings: ...
async def get_db(settings: Settings = Depends(get_settings)) -> asyncpg.Pool: ...
async def get_embedder() -> SentenceTransformer: ...
async def get_openrouter_client(settings=...) -> OpenRouterClient: ...
async def get_memory_store(db=..., embedder=..., client=...) -> MemoryStore: ...
async def get_router(embedder=..., client=..., db=...) -> EmbeddingRouter: ...
async def get_capability_gate(settings=...) -> CapabilityGate: ...
async def get_graph(request: Request) -> CompiledGraph: ...  # from app.state
```

## Session Management

- Each Telegram `chat_id` maps to a session. `str(chat_id)` is used as the
  LangGraph `thread_id`.
- The LangGraph `AsyncPostgresSaver` stores graph state keyed by `thread_id`.
  No in-memory session dict — state survives server restarts.
- Pending confirmation timeout: a background `asyncio.Task` is created when a
  graph is interrupted. After `CONFIRM_TIMEOUT_SECONDS`, the task calls
  `graph.aupdate_state(config, {"error": "confirmation_expired"})` and sends
  a "Confirmation expired" message to the Telegram chat.
- One active graph invocation per session at a time. If a new message arrives
  while the graph is running, reply "A task is already in progress." and discard
  the update.

## FastAPI Lifespan

`ze/api/app.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Shared resources
    pool         = await create_pool(settings.database_url)
    embedder     = load_embedder(settings.embedding_model)   # ze/embeddings.py
    http_client  = httpx.AsyncClient(http2=True)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    graph = build_graph(
        checkpointer=checkpointer,
        pool=pool,
        embedder=embedder,
        http_client=http_client,
        settings=settings,
    )

    bot = Bot(token=settings.telegram_bot_token)
    await bot.set_webhook(
        url=f"{settings.public_url}/telegram/webhook",
        secret_token=settings.telegram_webhook_secret,
    )

    app.state.pool        = pool
    app.state.embedder    = embedder
    app.state.http_client = http_client
    app.state.graph       = graph
    app.state.bot         = bot

    # SIGHUP → reload capability gate config
    signal.signal(signal.SIGHUP, lambda *_: capability_gate.reload())

    yield

    await bot.session.close()
    await http_client.aclose()
    await pool.close()
```

## CORS

Not required — there is no browser client. CORS middleware is omitted until a
Telegram Mini App phase is introduced.

When a Mini App is added, re-enable with:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Configuration

```
ZE_API_KEY=                        # static bearer token for REST endpoints
DATABASE_URL=                      # asyncpg-compatible postgres URL
CONFIRM_TIMEOUT_SECONDS=900        # 15 minutes
TELEGRAM_BOT_TOKEN=                # token from @BotFather
TELEGRAM_WEBHOOK_SECRET=           # arbitrary secret used to verify Telegram POSTs
PUBLIC_URL=                        # public HTTPS base URL (e.g. https://ze.fly.dev)
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `fastapi` | Web framework, Depends |
| `uvicorn` | ASGI server |
| `httpx` | Shared AsyncClient passed to OpenRouterClient |
| `aiogram` | Telegram Bot API client (webhook + sending) |
| `ze.orchestration.graph` | `build_graph()` |
| `ze.capability.gate` | `CapabilityGate` (SIGHUP reload) |
| `ze.errors` | All Ze exceptions |
| `ze.logging` | Request-scoped logger with chat_id bound |

## Implementation Notes

- The Telegram handler in `ze/api/telegram.py` binds `chat_id` to the structlog
  context at request time. All log records for that session automatically carry it.
- Graph invocation: use `graph.ainvoke()` (not `astream_events`) since tokens are
  not streamed to the client individually. The typing action is sent before invoking;
  the full response is sent after completion.
- Validation of `agent` and `intent` in `PUT /capabilities/{agent}/{intent}`:
  compare against the loaded agent registry (`list_agents()`) and the known intent
  set per agent. Return HTTP 422 if unknown.
- The `routing_log` endpoint uses offset-based pagination (not cursor-based) for
  simplicity. With expected row counts in the thousands, this is fine.
- `TELEGRAM_WEBHOOK_SECRET` must be between 1–256 characters, only `A-Z`, `a-z`,
  `0-9`, `_`, and `-` (Telegram API constraint).

## Open Questions

All resolved.
