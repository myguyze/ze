# ze-web

React web client for Ze. Connects to `ze-api` over WebSocket for chat, renders server-driven UI components, and provides management pages for goals, contacts, reminders, news, and costs.

Architecture: [Feature-Sliced Design](https://feature-sliced.design/). See [docs/frontend.md](../../docs/frontend.md) and [specs/phases/082-ze-web-fsd/spec.md](../../specs/phases/082-ze-web-fsd/spec.md).

## Role in Ze

`ze-web` is the user's window into Ze. All conversational interaction happens here over WebSocket; management pages use the REST API via `@ze/client`. Server-driven UI components from agents render inline in the chat without requiring frontend deploys.

## Source layout

```
src/
├── app/           # bootstrap, router, providers, global styles
├── pages/         # thin route entry points (one slice per route)
├── widgets/       # composite screen sections
├── features/      # user actions (export-data, load-chat-history, …)
├── entities/      # domain nouns (goal, message, contact, …)
└── shared/        # UI kit, lib, API wiring, config
```

| Path | What it provides |
|------|------------------|
| `app/router/routes.ts` | Route registry — paths, lazy imports, nav meta |
| `widgets/chat-workspace/` | Main chat UI |
| `widgets/*-overview/` | Management list screens |
| `entities/message/` | Message bubbles, chat input |
| `entities/primitive-tree/` | Server-driven UI renderer |
| `shared/api/ws-client.ts` | WebSocket singleton |
| `shared/config/` | Server URL + API key (`localStorage`) |

## Dependencies

Stack: React 19, Vite, TypeScript, Tailwind CSS, TanStack Query, Zustand, `@ze/client`, `@ze/ui`.

## Running

```bash
make web          # bun dev server on :5173
make web-build    # production build
make dev-full     # backend + web app together
```

Configure server URL and API key in the onboarding flow or Settings. No `VITE_*` env vars.

## Quality

```bash
make test-web     # vitest
make lint-web     # ESLint (FSD import boundaries)
```

See [docs/testing.md](../../docs/testing.md). WebSocket protocol: [docs/native-interface.md](../../docs/native-interface.md).
