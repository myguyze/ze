# Frontend — Spec

## Purpose

Minimal, custom chat interface for Ze. Supports real-time token streaming,
confirmation modals with countdown timers for gated actions, draft review before
send, and per-message routing metadata behind a toggle.

## Responsibilities

- Connect to the Ze WebSocket on load and maintain the connection.
- Display streaming chat messages token-by-token as they arrive.
- Show a confirmation modal when the server sends `confirmation_request`.
- Show the countdown timer (15 min) in the confirmation modal.
- Show draft review panel for `draft_only` actions.
- Display routing metadata (agent, method, confidence) behind a toggle.
- Handle WebSocket reconnection with exponential backoff.
- Validate environment variables at build time.

## Out of Scope

- No authentication UI — API key is injected via `NEXT_PUBLIC_ZE_WS_URL` env.
- No settings or configuration UI (Phase 4).
- No mobile-native wrapper.
- No external component library.

## Component Tree

```
app/page.tsx                    (Server Component — metadata, layout shell)
└── components/chat/ChatClient.tsx    ('use client' boundary — owns all state)
    ├── components/chat/ChatWindow.tsx
    │   ├── components/chat/MessageBubble.tsx  (× N messages)
    │   └── components/chat/MessageInput.tsx
    └── components/overlays/ConfirmationModal.tsx   (rendered when awaiting)
        └── components/overlays/DraftReview.tsx     (rendered inside modal for edits)
```

`page.tsx` is a Server Component. It renders `<ChatClient />` which carries the
`'use client'` directive and owns the full interactive state tree.

## Component Specs

### `ChatClient.tsx` (`'use client'`)

Owns:
- `messages: ZeMessage[]` — full message history.
- `uiState: UiState` — current UI state machine.
- `pendingConfirmation: ConfirmationRequest | null` — the active confirmation payload.
- Renders `ChatWindow` and conditionally renders `ConfirmationModal`.
- Passes `sendMessage` and `sendConfirm` callbacks down from `useZeSocket`.

### `ChatWindow.tsx`

- Renders a scrollable list of `MessageBubble` components.
- Scrolls to bottom on new messages and on each token append.
- Passes `disabled` prop to `MessageInput` when `uiState !== 'idle'`.

### `MessageBubble.tsx`

Props: `message: ZeMessage`, `isStreaming: boolean`

- Renders message content with role-based styling (user vs agent).
- Shows an animated cursor while `isStreaming` is true.
- Shows an info icon (ℹ) that toggles metadata visibility on click.
- Metadata panel (hidden by default): agent name, routing method, confidence score.

### `MessageInput.tsx`

Props: `onSend: (text: string) => void`, `disabled: boolean`

- Textarea with submit on Enter (Shift+Enter for newline).
- Disabled and visually dimmed when `disabled` is true.
- Clears on submit.

### `ConfirmationModal.tsx`

Props:
```typescript
confirmation: ConfirmationRequest
onConfirm: () => void
onReject: () => void
onEdit: (editedContent: string) => void
timeoutSeconds: number              // 900 from env
```

- Full-screen overlay, not dismissible by clicking outside.
- Shows the draft content in a read-only code/text block by default.
- "Edit" button switches to `DraftReview` (editable textarea).
- Countdown timer: `MM:SS` format, counts down from `timeoutSeconds`.
- On timeout: disables Yes/No/Edit buttons, shows "Confirmation expired" message.

### `DraftReview.tsx`

Props: `initialContent: string`, `onSave: (edited: string) => void`, `onCancel: () => void`

- Editable textarea pre-filled with the draft.
- "Send" button calls `onSave` with edited content.
- "Cancel" returns to the read-only confirmation view.

## `useZeSocket` Hook

`hooks/useZeSocket.ts`

```typescript
interface UseZeSocketReturn {
  sendMessage: (content: string) => void
  sendConfirm: (decision: "yes" | "no" | "edit", editContent?: string) => void
  messages: ZeMessage[]
  uiState: UiState
  pendingConfirmation: ConfirmationRequest | null
}

export function useZeSocket(sessionId: string): UseZeSocketReturn
```

**Responsibilities:**
- Open WebSocket to `${env.NEXT_PUBLIC_ZE_WS_URL}/ws/${sessionId}`.
- On `token` message: append chunk to the last message in `messages` (streaming).
- On `done` message: mark last message as complete, update metadata, set `uiState='idle'`.
- On `confirmation_request`: set `pendingConfirmation`, set `uiState='awaiting_confirmation'`.
- On `confirmation_expired`: clear `pendingConfirmation`, set `uiState='idle'`, append system message.
- On `error`: append error message, set `uiState='idle'`.
- On disconnect: reconnect with exponential backoff (base 1s, factor ×2, max 30s, ±20% jitter).
- `sendMessage`: appends user message to `messages`, sets `uiState='streaming'`, sends `UserMessage` over WS.
- `sendConfirm`: sends `ConfirmMessage`, sets `uiState='streaming'`, clears `pendingConfirmation`.

**Reconnection behaviour:** On disconnect, the hook attempts to reconnect silently.
During reconnect, `uiState` is set to `'reconnecting'` and input is disabled.
After max backoff is reached (30s), the hook stops retrying and sets
`uiState='disconnected'`. User must reload the page.

## TypeScript Types

`types/index.ts`

```typescript
export type UiState =
  | "idle"
  | "streaming"
  | "awaiting_confirmation"
  | "draft_review"
  | "reconnecting"
  | "disconnected"
  | "error"

export interface ZeMessage {
  id: string
  role: "user" | "agent" | "system"
  content: string
  isStreaming: boolean
  meta?: AgentMeta
}

export interface AgentMeta {
  agent: string
  routingMethod: "embedding" | "haiku"
  confidence: number | null
}

export interface ConfirmationRequest {
  type: "confirmation_request"
  draft: string
  agent: string
  action: string
}

// WS message union — exhaustive
export type WsServerMessage =
  | { type: "token";                content: string }
  | { type: "done";                 agent: string; routing_method: string; confidence: number | null }
  | { type: "confirmation_request"; draft: string; agent: string; action: string }
  | { type: "confirmation_expired" }
  | { type: "error";                message: string }
```

## Environment Variables

`lib/env.ts` — validated at build time with Zod:

```typescript
import { z } from "zod"

const schema = z.object({
  NEXT_PUBLIC_ZE_WS_URL: z.string().url(),
  NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS: z.coerce.number().default(900),
})

export const env = schema.parse({
  NEXT_PUBLIC_ZE_WS_URL: process.env.NEXT_PUBLIC_ZE_WS_URL,
  NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS: process.env.NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS,
})
```

If validation fails, the Next.js build fails with a clear error. No silent
`undefined` environment variables at runtime.

## Utilities

`lib/utils.ts`

```typescript
import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

## Tailwind Configuration

`tailwind.config.ts` — extend with Ze-specific design tokens:

```typescript
theme: {
  extend: {
    colors: {
      "user-bubble":  "#e2e8f0",
      "agent-bubble": "#1e293b",
      "muted":        "#64748b",
    },
    fontFamily: {
      sans: ["Inter", "system-ui", "sans-serif"],
      mono: ["JetBrains Mono", "monospace"],
    },
  },
}
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `next` (14) | App Router, Server Components |
| `react`, `react-dom` | UI |
| `tailwindcss`, `postcss`, `autoprefixer` | Styling |
| `clsx`, `tailwind-merge` | `cn()` utility |
| `zod` | Env validation in `lib/env.ts` |

No UI component library. No state management library (React `useState` + custom hook is sufficient).

## Implementation Notes

- Session ID: generate a stable UUID on first load and persist in `localStorage`.
  Subsequent visits reconnect to the same session, so pending confirmations survive
  page refreshes (they are checkpointed server-side).
- Token buffering in `useZeSocket`: maintain a `streamingMessageId` ref. On each
  `token` event, find the message by id in state and append content. Do not create
  a new message per token.
- The `ConfirmationModal` countdown uses `setInterval` cleared in `useEffect`
  cleanup. It counts down from `env.NEXT_PUBLIC_CONFIRM_TIMEOUT_SECONDS`.
- `page.tsx` generates a stable `sessionId` server-side (via a cookie read) and
  passes it to `<ChatClient sessionId={...} />`. This avoids the session ID
  changing on every client render.

## Open Questions

All resolved.
