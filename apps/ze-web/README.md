# ze-web

React web client for Ze. Connects to `ze-api` over WebSocket for chat, renders server-driven UI components, and provides management pages for goals, contacts, reminders, news, and costs.

## Responsibilities

| Path | What it provides |
|---|---|
| `src/features/chat/` | Chat session, message list, confirmation bar, typing indicator |
| `src/features/websocket/` | WebSocket connection, protocol types, refresh handler |
| `src/components/server-driven/` | Component renderer for agent-emitted UI descriptors |
| `src/pages/` | Chat, goals, contacts, reminders, news, costs, settings, onboarding |
| `src/lib/api.ts` | REST client for management endpoints |
| `src/app/router.tsx` | Client-side routing |

## Dependencies

No Python dependencies. Connects to `ze-api` at runtime over WebSocket (`/ws`) and REST.

Stack: React 19, Vite, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Zustand.

## Running

```bash
make web          # bun dev server on :5173
make web-build    # production build
make dev-full     # backend + web app together
```

Set `VITE_ZE_API_URL` and `VITE_ZE_API_KEY` (see `src/config/AppConfig.ts`) to point at your backend.

## Testing

From the repo root:

```bash
make test-web
```

See [docs/testing.md](../../docs/testing.md).

WebSocket protocol reference: [docs/native-interface.md](../../docs/native-interface.md).
