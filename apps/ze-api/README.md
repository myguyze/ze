# ze-api

Deployment unit for Ze. Wires all packages together, exposes the WebSocket chat endpoint and REST management API, runs background jobs, and handles Google integrations.

## Responsibilities

| Module | What it provides |
|---|---|
| `api/` | FastAPI app, WebSocket (`/ws`), REST routes, schemas |
| `bootstrap.py` | Agent DI wiring via plugin `agent_module_paths()` |
| `interface/native.py` | `NativeAppInterface` — WebSocket + ntfy delivery |
| `onboarding/` | Postgres-backed onboarding store, persistence, and reset |
| `hooks/` | Agent harness hooks (tool-call cap, component collection, cost cap) |
| `container.py` | `ZeContainer` — DI wiring, registers all `ZePlugin` implementations |
| `settings.py` | `Settings` (Pydantic BaseSettings + YAML) |
| `config/config.yaml` | Models, contacts, proactive schedules |
| `config/persona.yaml` | Persona profiles and dials |
| `migrations/` | Alembic SQL migrations |

Agents and proactive jobs live in plugin packages (`ze-personal`, `ze-email`, `ze-calendar`, etc.) — not in `ze-api`.

## Dependencies

```mermaid
graph LR
    api[ze-api] --> core[ze-core]
    api --> sdk[ze-sdk]
    api --> memory[ze-memory]
    api --> correlation[ze-correlation]
    api --> personal[ze-personal]
    api --> email[ze-email]
    api --> calendar[ze-calendar]
    api --> prospecting[ze-prospecting]
    api --> google[ze-google]
    api --> browser[ze-browser]
    api --> news[ze-news]
    api --> notif[ze-notifications]
    api --> comp[ze-components]
    api --> onboarding[ze-onboarding]
```

## Running

```bash
make dev          # uvicorn --reload on :8000
make dev-eval     # REST API without background jobs (for running evals)
make dev-full     # backend + React web app together
```

## WebSocket protocol

Connect at `ws://<host>:8000/ws` with `Authorization: Bearer <ZE_API_KEY>` header or `?token=<ZE_API_KEY>` query param.

**Send** (user turn):
```json
{"type": "message", "text": "What's on my calendar today?", "thread_id": "<uuid>"}
```

**Receive** (assistant response):
```json
{"type": "message", "message": {"role": "assistant", "text": "...", "components": [...]}}
```

**Receive** (confirmation request):
```json
{"type": "confirm_request", "id": "<uuid>", "prompt": "...", "actions": [{"label": "Approve", "payload": "yes"}]}
```

**Send** (confirmation reply — same as a regular message on the original thread):
```json
{"type": "message", "text": "yes", "thread_id": "<original-thread-id>"}
```

Full protocol reference: [docs/native-interface.md](../../docs/native-interface.md).

## REST endpoints

| Route | Description |
|---|---|
| `GET /messages` | Unread message list (WebSocket replay fallback) |
| `GET /capabilities` | List capability overrides |
| `PATCH /capabilities/{agent}/{action}` | Update a capability mode |
| `GET /memory/facts` | Inspect stored facts |
| `GET /memory/profile` | Get current user profile |
| `GET /routing/log` | Routing decision log |
| `GET /costs` | Token usage and cost breakdown |
| `GET /workflows` | List workflows |

All routes require `Authorization: Bearer <ZE_API_KEY>`.

## Configuration

See the root [README](../../README.md#configuration) for all environment variables.

## Testing

From the repo root:

```bash
make test        # alias for test-api
make test-api
```

See [docs/testing.md](../../docs/testing.md).
