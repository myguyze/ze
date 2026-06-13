# apps/

Runnable deployment units. These packages wire everything together — they import from
both `core/` and `plugins/` but are never imported by either.

---

## Packages

| Package | Description |
|---------|-------------|
| [ze-api](ze-api/) | FastAPI/WebSocket backend — HTTP API, WebSocket chat endpoint, background jobs, plugin wiring |
| [ze-web](ze-web/) | React web client (Vite + TypeScript + Tailwind + shadcn/ui) |

## ze-api

The only package that instantiates `ZeContainer` and registers all `ZePlugin`
implementations. It owns:

- The WebSocket endpoint (`/ws`) and REST management routes
- `NativeAppInterface` — WebSocket + ntfy push delivery
- Alembic migrations (`migrations/versions/`)
- `config/config.yaml` and `config/persona.yaml`

```bash
make dev        # uvicorn --reload on :8000
make migrate    # apply pending migrations
make test       # run ze-api tests
```

## ze-web

React SPA. Connects to `ze-api` over WebSocket at `/ws`. Has no Python dependencies —
built and run with the Bun JavaScript runtime.

```bash
make web        # bun dev server on :5173
make web-build  # production build
```

## Dependency graph

```
ze-api  ←  ze-core, ze-memory, ze-personal, ze-email, ze-calendar,
            ze-prospecting, ze-browser, ze-news, ze-notifications,
            ze-components, ze-google
ze-web  ←  (React — connects to ze-api over WebSocket, no Python deps)
```
