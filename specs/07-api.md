# API — Spec

## Purpose

FastAPI application that exposes a WebSocket endpoint for real-time chat, REST
endpoints for configuration and memory management, and owns session lifecycle.
It is the only entry point into Ze — all external communication goes through here.

## Responsibilities

- Accept and maintain WebSocket connections from the frontend.
- Authenticate requests via static API key (`ZE_API_KEY`).
- Dispatch incoming WebSocket messages into the LangGraph orchestration graph.
- Stream LangGraph token output back to the client token-by-token.
- Resume paused graphs when the client sends a `confirm` message.
- Expire paused graphs after `CONFIRM_TIMEOUT_SECONDS` (default 900).
- Expose REST endpoints for capabilities, memory, and routing log.
- Wire all dependencies via FastAPI `Depends()` in `dependencies.py`.
- Manage FastAPI lifespan: DB pool, embedding model, graph, checkpointer.

## Out of Scope

- Does not implement business logic — delegates to orchestration and domain modules.
- Does not serve the frontend (Next.js is a separate process).
- Does not handle Google OAuth2 flows (Phase 3).

## Endpoints

### WebSocket

```
WS /ws/{session_id}
```

Authentication: `Authorization: Bearer <ZE_API_KEY>` header on the upgrade request.

**Client → Server messages** (Pydantic models in `api/schemas.py`):

```python
class UserMessage(BaseModel):
    type: Literal["message"]
    content: str

class ConfirmMessage(BaseModel):
    type: Literal["confirm"]
    decision: Literal["yes", "no", "edit"]
    edit_content: str | None = None   # populated when decision == "edit"

WsClientMessage = Annotated[
    UserMessage | ConfirmMessage,
    Field(discriminator="type")
]
```

**Server → Client messages**:

```python
class TokenMessage(BaseModel):
    type: Literal["token"]
    content: str

class ConfirmationRequest(BaseModel):
    type: Literal["confirmation_request"]
    draft: str
    agent: str
    action: str                         # e.g. "send email to alice@example.com"

class DoneMessage(BaseModel):
    type: Literal["done"]
    agent: str
    routing_method: str                 # "embedding" | "haiku"
    confidence: float | None

class ErrorMessage(BaseModel):
    type: Literal["error"]
    message: str

class ConfirmationExpiredMessage(BaseModel):
    type: Literal["confirmation_expired"]

WsServerMessage = (
    TokenMessage | ConfirmationRequest | DoneMessage |
    ErrorMessage | ConfirmationExpiredMessage
)
```

**Message flow:**

```
Client sends UserMessage
    → graph.ainvoke(state, config={thread_id: session_id})
    → tokens streamed back as TokenMessage
    → on interrupt: ConfirmationRequest sent
    → client sends ConfirmMessage
    → graph.ainvoke(None, config)  # resume
    → DoneMessage sent on completion
    → ErrorMessage sent on unhandled exception
```

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

- Each WebSocket connection maps to a `session_id` (URL path parameter).
- The LangGraph `AsyncPostgresSaver` stores graph state keyed by `session_id`.
  No in-memory session dict — state survives server restarts.
- Pending confirmation timeout: a background `asyncio.Task` is created when a
  graph is interrupted. After `CONFIRM_TIMEOUT_SECONDS`, the task calls
  `graph.aupdate_state(config, {"error": "confirmation_expired"})` and sends
  a `ConfirmationExpiredMessage` to the client if the WebSocket is still open.
- One active graph invocation per session at a time. If a new `UserMessage`
  arrives while a graph is running, return `ErrorMessage(type="error",
  message="A task is already in progress.")`.

## FastAPI Lifespan

`ze/api/app.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Shared resources
    pool       = await create_pool(settings.database_url)
    embedder   = load_embedder(settings.embedding_model)   # ze/embeddings.py
    http_client = httpx.AsyncClient(http2=True)
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    graph = build_graph(
        checkpointer=checkpointer,
        pool=pool,
        embedder=embedder,
        http_client=http_client,
        settings=settings,
    )

    app.state.pool         = pool
    app.state.embedder     = embedder
    app.state.http_client  = http_client
    app.state.graph        = graph

    # SIGHUP → reload capability gate config
    signal.signal(signal.SIGHUP, lambda *_: capability_gate.reload())

    yield

    await http_client.aclose()
    await pool.close()
```

## CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # ["http://localhost:3000"] in dev
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`CORS_ORIGINS` in `.env` — comma-separated list.

## Configuration

```
ZE_API_KEY=                        # static bearer token for all requests
DATABASE_URL=                      # asyncpg-compatible postgres URL
CONFIRM_TIMEOUT_SECONDS=900        # 15 minutes
CORS_ORIGINS=http://localhost:3000
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `fastapi` | Web framework, WebSocket, Depends |
| `uvicorn` | ASGI server |
| `httpx` | Shared AsyncClient passed to OpenRouterClient |
| `ze.orchestration.graph` | `build_graph()` |
| `ze.capability.gate` | `CapabilityGate` (SIGHUP reload) |
| `ze.errors` | All Ze exceptions |
| `ze.logging` | Request-scoped logger with session_id bound |

## Implementation Notes

- The WebSocket handler in `ws.py` binds `session_id` to the structlog context
  at connection time. All log records for that session automatically carry it.
- Token streaming from LangGraph: use `graph.astream_events()` with `version="v2"`.
  Filter for `on_chat_model_stream` events to extract token chunks.
- Validation of `agent` and `intent` in `PUT /capabilities/{agent}/{intent}`:
  compare against the loaded agent registry (`list_agents()`) and the known intent
  set per agent. Return HTTP 422 if unknown.
- The `routing_log` endpoint uses offset-based pagination (not cursor-based) for
  simplicity. With expected row counts in the thousands, this is fine.

## Open Questions

All resolved.
