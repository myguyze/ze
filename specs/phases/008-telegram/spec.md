# Telegram Bot — Spec

## Purpose

Telegram bot that serves as the primary user interface for Ze. The bot receives
messages from the user, dispatches them to the LangGraph orchestration graph, and
sends responses back via the Telegram Bot API. Confirmation flows use inline keyboards.

## Responsibilities

- Register a webhook with Telegram pointing at `POST /telegram/webhook`.
- Verify every incoming update using the `X-Telegram-Bot-Api-Secret-Token` header.
- Dispatch text messages to the orchestration graph, keyed by `chat_id`.
- Send a typing action while the graph is running, then send the full response.
- Present capability confirmations as an inline keyboard with Yes / No / Edit buttons.
- Handle the "Edit" flow via a ForceReply message.
- Resume paused graphs on inline keyboard callbacks.
- Notify the user when a pending confirmation expires.
- Handle long responses by splitting at Telegram's 4096-character message limit.

## Out of Scope

- Does not implement business logic — delegates entirely to `ze/orchestration`.
- Does not implement a Telegram Mini App (future phase).
- Does not support group chats — single-user only, `chat_id` must match
  `TELEGRAM_ALLOWED_CHAT_ID` or the message is silently ignored.
- Does not handle documents, video, stickers, or GIFs — text, voice, and photos
  only (see `19-multimodal-input.md`).

## Module Location

```
ze/api/telegram.py      # FastAPI router: POST /telegram/webhook
ze/telegram/            # Bot logic (separated from API layer)
    bot.py              # ZeBot class — owns aiogram Bot instance, all send helpers
    handlers.py         # message_handler, callback_handler, edit_reply_handler
    keyboards.py        # InlineKeyboardMarkup builders
    session.py          # ActiveSessionStore — tracks in-progress graph invocations
```

## Authentication

The webhook is registered with a `secret_token` (env: `TELEGRAM_WEBHOOK_SECRET`).
Telegram includes this value in the `X-Telegram-Bot-Api-Secret-Token` header on
every POST. FastAPI checks it before passing the update to any handler. Mismatched
or absent tokens return HTTP 401 with no body.

Single-user enforcement: `TELEGRAM_ALLOWED_CHAT_ID` (int) is read from settings.
Any update whose `chat_id` does not match is acknowledged (HTTP 200) and discarded
— no error is sent back.

## Update Handling

### Text message (`message` update)

```
1. Verify secret_token header.
2. Check chat_id against TELEGRAM_ALLOWED_CHAT_ID.
3. Check ActiveSessionStore — if a graph is already running for this chat_id:
       reply "A task is already in progress." and return.
4. Check if an edit-reply is pending for this chat_id (ForceReply state):
       if yes, treat the message as a ConfirmMessage(decision="edit", edit_content=text)
       and go to step 7 (resume graph).
5. Register chat_id in ActiveSessionStore.
6. sendChatAction(chat_id, "typing").
7. graph.ainvoke(state, config={thread_id: str(chat_id)}).
8. On completion: send full response text (split if > 4096 chars).
   Clear chat_id from ActiveSessionStore.
9. On graph interrupt (confirmation required):
       send ConfirmationRequest message (see below).
       start timeout background task.
10. On unhandled exception: send "Something went wrong. Try again." and clear session.
```

### Inline keyboard callback (`callback_query` update)

```
1. Verify secret_token header and chat_id.
2. Parse callback_query.data:
     "confirm:yes"  → decision = "yes"
     "confirm:no"   → decision = "no"
     "confirm:edit" → send ForceReply message, store ForceReply state, return
3. answerCallbackQuery (clears the spinner on the button).
4. Edit the confirmation message to show the chosen decision (prevents re-clicks).
5. Register chat_id in ActiveSessionStore.
6. graph.ainvoke(None, config={thread_id: str(chat_id)})  # resume
7. Send full response. Clear session.
```

## Confirmation Flow

When the orchestration graph is interrupted by `capability_check`, the bot sends:

```
⚠️ Confirmation required

Agent:   email
Action:  send email to alice@example.com
Draft:
────────────────────
<draft content here>
────────────────────

[✅ Yes]  [❌ No]  [✏️ Edit]
```

The inline keyboard payload uses the `confirm:<decision>` format.

**Edit path:**

On `confirm:edit` callback:
1. Edit the confirmation message to remove the keyboard (prevent double-tap).
2. Send: `Please reply with your edited version:` using `ForceReply`.
3. Store `ForceReply` state for this `chat_id`.
4. User replies (Telegram pre-fills the reply field due to ForceReply).
5. Bot receives the reply as a normal `message` update.
6. Edit-reply handler detects the ForceReply state, extracts text, resumes graph
   with `ConfirmMessage(decision="edit", edit_content=text)`.

## Confirmation Expiry

When `CONFIRM_TIMEOUT_SECONDS` elapses without a callback:
- `graph.aupdate_state(config, {"error": "confirmation_expired"})` is called.
- Bot sends: `⏱ Confirmation expired. The action was cancelled.`
- ForceReply state (if any) is cleared.
- ActiveSessionStore entry is cleared.

## Response Formatting

- Plain text responses are sent as-is.
- Responses longer than 4096 characters are split at the nearest newline before
  the limit and sent as sequential messages.
- Markdown formatting: use `parse_mode=ParseMode.MARKDOWN_V2` only when the agent
  explicitly signals markdown output (future: via `AgentState` flag). Default is
  plain text to avoid escaping issues.

## `ZeBot` Class

`ze/telegram/bot.py`

```python
class ZeBot:
    def __init__(self, bot: Bot, graph: CompiledGraph, settings: Settings): ...

    async def handle_message(self, message: Message) -> None: ...
    async def handle_callback(self, query: CallbackQuery) -> None: ...
    async def handle_edit_reply(self, message: Message) -> None: ...

    async def _send_response(self, chat_id: int, text: str) -> None:
        # Splits text at 4096-char boundary and calls bot.send_message.

    async def _send_confirmation(self, chat_id: int, state: AgentState) -> None:
        # Builds InlineKeyboardMarkup and sends the confirmation message.

    async def _resume_graph(self, chat_id: int, decision: str,
                            edit_content: str | None = None) -> None:
        # Constructs ConfirmMessage, calls graph.ainvoke(None, config).
```

## `ActiveSessionStore`

`ze/telegram/session.py`

In-memory set of `chat_id` values with an active graph invocation. Operations:

```python
class ActiveSessionStore:
    def is_active(self, chat_id: int) -> bool: ...
    def mark_active(self, chat_id: int) -> None: ...
    def clear(self, chat_id: int) -> None: ...
```

Not persisted — if the server restarts mid-invocation, the user can send a new
message and it will be processed normally (the graph state is persisted in Postgres).

## Settings

```
TELEGRAM_BOT_TOKEN=           # token from @BotFather
TELEGRAM_WEBHOOK_SECRET=      # 1-256 chars, [A-Za-z0-9_-]
TELEGRAM_ALLOWED_CHAT_ID=     # your personal Telegram chat_id (int)
PUBLIC_URL=                   # public HTTPS base URL registered as webhook target
```

`TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` are secrets — store in `.env`
and in Fly.io secrets. Never commit to the repo.

## Dependencies

| Package | Purpose |
|---------|---------|
| `aiogram` (3.x) | Async Telegram Bot API client |
| `ze.orchestration.graph` | `build_graph()`, `CompiledGraph` |
| `ze.api.schemas` | `AgentState` for confirmation payload |
| `ze.errors` | Ze exception hierarchy |
| `ze.logging` | `get_logger(__name__)`, `bind_context(chat_id=...)` |

## Implementation Notes

- Use aiogram's `Bot` class directly (not the Dispatcher/FSM machinery) — the
  webhook is handled by FastAPI, not aiogram's built-in web server.
- The `ForceReply` state is stored in a plain `dict[int, bool]` on `ZeBot`.
  This is safe for single-user use. If the server restarts while ForceReply is
  pending, the next message from the user falls through to normal handling
  (the graph resumes as a new user message, not ideal but acceptable).
- `sendChatAction` with `"typing"` is valid for up to 5 seconds. For graph runs
  that take longer, repeat the call every 4 seconds using `asyncio.create_task`.
  Cancel the task after the graph completes.
- When registering the webhook, pass `allowed_updates=["message", "callback_query"]`
  to suppress irrelevant update types.

## Open Questions

All resolved.
