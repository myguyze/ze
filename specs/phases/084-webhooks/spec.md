# Phase 86 — Webhook Infrastructure

**Status:** Pending
**Depends on:** Phase 85 (Ze Messaging Hub)
**Packages touched:** `core/ze-communication`, `core/ze-plugin`, `apps/ze-api`, `integrations/ze-google`

---

## What this is

Ze needs a generic webhook infrastructure that any plugin can register handlers against.
This phase builds that base — a single `POST /api/v0/webhooks/{source}` endpoint, a
`WebhookDispatcher` that routes by source key, and two handler paths:

1. **Channel path** — `InboundChannel` implementations declare a `WebhookVerifier`; the
   dispatcher routes to them when the source key matches a registered channel type. Gmail
   push is the first integration.
2. **Plugin path** — any `ZePlugin` can register `WebhookHandler` objects for non-channel
   sources (e.g. Trading212 transaction events, future CRM callbacks). The dispatcher falls
   through to plugin handlers when no channel matches.

Both paths share the same `WebhookPayload` type and the same dedup/auth flow. Adding a new
integration later requires no changes to routing or `ze-api`.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Endpoint shape | `POST /api/v0/webhooks/{source}` | Single route; `source` is a free-form key matching either a `ChannelType` value or a plugin-registered key |
| Auth | Per-handler verifier, not `require_api_key` | External callers (Google, Trading212, etc.) use their own signing schemes, not our bearer token |
| Two handler paths | Channel path + plugin path in `WebhookDispatcher` | Channels cover push messaging; plugins cover data ingestion / automation triggers |
| Channel contract | `WebhookVerifier` on `InboundChannel` in `ze-communication` | Verification stays with the channel implementation |
| Plugin contract | `WebhookHandler` Protocol + `ZePlugin.webhook_handlers()` in `ze-plugin` | Plugins own their handlers; dispatcher collects at startup |
| Dispatcher | `WebhookDispatcher` in `ze-api` | Owns routing: channel registry → plugin handlers → 404 |
| Agent trigger | `container.invoke()` with synthetic session | Reuses the LangGraph invocation path; memory writes and cost tracking apply |
| Dedup | `EventDeduplicator` (in-memory TTLCache) keyed on source + event_id | At-least-once delivery from external services; no DB needed |
| Webhook secret storage | `.env` / `ZeApiSettings` | One secret per source; never in YAML |

---

## Core contracts (`core/ze-communication` + `core/ze-plugin`)

### `ze_communication/webhook.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WebhookPayload:
    source: str            # matches ChannelType value or WebhookHandler.source_key
    raw_body: bytes
    headers: dict[str, str]


class WebhookVerifier(ABC):
    """Implemented by each InboundChannel that supports push delivery."""

    @abstractmethod
    def verify(self, payload: WebhookPayload) -> bool:
        """Return True if the payload is authentic. Raise or return False otherwise."""
        ...

    @abstractmethod
    async def parse(self, payload: WebhookPayload) -> list["InboundMessage"]:
        """Parse a verified payload into zero or more InboundMessages."""
        ...
```

`InboundChannel` gains an optional push hook:

```python
class InboundChannel(Channel):
    @property
    def supports_push(self) -> bool:
        return False

    def webhook_verifier(self) -> "WebhookVerifier | None":
        """Return a verifier when supports_push is True, else None."""
        return None

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
```

### `ze_plugin/webhook.py`

```python
from typing import Protocol, runtime_checkable
from ze_communication.webhook import WebhookPayload


@runtime_checkable
class WebhookHandler(Protocol):
    """Implemented by plugins that receive non-channel webhook events."""

    source_key: str
    """Unique identifier for this handler, matched against the {source} path segment."""

    def verify(self, payload: WebhookPayload) -> bool:
        """Return True if the payload is authentic."""
        ...

    async def handle(self, payload: WebhookPayload) -> None:
        """Process a verified payload. Fire-and-forget; errors are logged and swallowed."""
        ...
```

`ZePlugin` gains a hook:

```python
class ZePlugin(ABC):
    ...
    def webhook_handlers(self) -> list[WebhookHandler]:
        """Return webhook handlers owned by this plugin. Default: none."""
        return []
```

`ze_sdk/channels.py` re-exports: `WebhookPayload`, `WebhookVerifier`.
`ze_sdk/__init__.py` (or `ze_sdk/plugin.py`) re-exports: `WebhookHandler`.

---

## `apps/ze-api`: dispatcher + route

### Route

```python
# ze_api/api/routes/webhooks.py

@router.post(
    "/webhooks/{source}",
    status_code=200,
    summary="Receive inbound webhook from an external source",
    description="Authenticated by the source's own signing scheme, not the Ze API key.",
    operation_id="receive_webhook",
)
async def receive_webhook(
    source: str,
    request: Request,
    dispatcher: WebhookDispatcher = Depends(get_webhook_dispatcher),
) -> dict:
    raw_body = await request.body()
    headers = dict(request.headers)
    await dispatcher.dispatch(source, raw_body, headers)
    return {"ok": True}
```

### WebhookDispatcher

```python
# ze_api/webhook.py

class WebhookDispatcher:
    def __init__(
        self,
        channel_registry: ChannelRegistry,
        plugin_handlers: dict[str, WebhookHandler],  # built at startup from all ZePlugin.webhook_handlers()
        container: ZeContainer,
        deduplicator: EventDeduplicator,
    ) -> None: ...

    async def dispatch(
        self, source: str, raw_body: bytes, headers: dict[str, str]
    ) -> None:
        payload = WebhookPayload(source=source, raw_body=raw_body, headers=headers)

        # Channel path
        channel = channel_registry.get_inbound(ChannelType(source))
        if channel is not None and channel.supports_push:
            verifier = channel.webhook_verifier()
            if not verifier.verify(payload):
                raise WebhookAuthError(source)
            messages = await verifier.parse(payload)
            for msg in messages:
                if self.deduplicator.is_duplicate(source, msg.message_id):
                    continue
                self.deduplicator.mark_seen(source, msg.message_id)
                asyncio.create_task(self._trigger_messenger(msg))
            return

        # Plugin path
        handler = self.plugin_handlers.get(source)
        if handler is not None:
            if not handler.verify(payload):
                raise WebhookAuthError(source)
            asyncio.create_task(handler.handle(payload))
            return

        raise WebhookSourceNotFoundError(source)

    async def _trigger_messenger(self, msg: InboundMessage) -> None:
        # Build a synthetic session and invoke MessengerAgent via container.invoke()
        ...
```

### EventDeduplicator

In-memory `cachetools.TTLCache` keyed on `(source, event_id)`, capped at 10 000 entries,
TTL 24h. No DB needed.

### Startup wiring

`ZeContainer` collects plugin handlers at startup:

```python
plugin_handlers = {
    h.source_key: h
    for plugin in self._plugins
    for h in plugin.webhook_handlers()
}
dispatcher = WebhookDispatcher(channel_registry, plugin_handlers, self, deduplicator)
```

---

## `integrations/ze-google`: Gmail push (first integration)

### How Gmail push works

1. Create a Google Cloud Pub/Sub topic.
2. Create a Push subscription pointing to `{PUBLIC_URL}/api/v0/webhooks/email`.
3. Call `gmail.users().watch(userId="me", body={topicName: ..., labelIds: ["INBOX"]})`.
4. Gmail POSTs `{"message": {"data": "<base64>", "messageId": "..."}}` on inbox change.
5. Decode `data` → `{"emailAddress": "...", "historyId": "..."}`.
6. Call `gmail.users().history().list(startHistoryId=...)` to get new message IDs.
7. Respond `200 OK` within 10s or Google retries.

### GmailWebhookVerifier

Google authenticates via a Google-signed OIDC JWT in the `Authorization` header.
Verify: decode JWT, check signature against Google's public keys, confirm `aud` matches
`{PUBLIC_URL}/api/v0/webhooks/email`.

```python
# ze_google/webhook.py

class GmailWebhookVerifier(WebhookVerifier):
    def __init__(self, credentials: GoogleCredentials, public_url: str) -> None: ...

    def verify(self, payload: WebhookPayload) -> bool:
        # Verify Google OIDC JWT in Authorization header
        ...

    async def parse(self, payload: WebhookPayload) -> list[InboundMessage]:
        # Decode base64 data → historyId
        # Call history.list(startHistoryId=...) to get new message IDs
        # Fetch each message, parse to InboundMessage
        ...
```

### GmailChannel changes

```python
class GmailChannel(InboundChannel):
    def __init__(self, credentials: GoogleCredentials, public_url: str | None = None) -> None:
        self._creds = credentials
        self._public_url = public_url

    @property
    def supports_push(self) -> bool:
        return self._public_url is not None

    def webhook_verifier(self) -> GmailWebhookVerifier | None:
        if self._public_url is None:
            return None
        return GmailWebhookVerifier(self._creds, self._public_url)

    async def register_push(self, topic_name: str) -> None:
        service = self._creds.gmail()
        await asyncio.to_thread(
            lambda: service.users().watch(
                userId="me",
                body={"topicName": topic_name, "labelIds": ["INBOX"]},
            ).execute()
        )
```

`MessengerPlugin` passes `public_url` from `ZeApiSettings` to `GmailChannel` at
construction. When `PUBLIC_URL` is unset, `supports_push` is `False` and polling continues.

---

## Inbound-poll job changes

The inbound-poll job skips channels that receive push:

```python
for channel in registry.inbound_channels():
    if channel.supports_push:
        continue  # messages arrive via webhook
    new_msgs = await channel.poll_new_messages(since=last_checked)
    ...
```

Fully backward-compatible: unset `PUBLIC_URL` → polling; set → push.

---

## Settings

```python
# ze_api/settings.py additions

gmail_pubsub_topic: str | None = None   # e.g. "projects/my-project/topics/ze-gmail"
```

`PUBLIC_URL` already exists in settings and is passed to `GmailChannel`.

---

## Gmail push registration command

```bash
python -m ze_api.cli register_gmail_push
```

Calls `GmailChannel.register_push(topic_name)`. Gmail watch expires after 7 days;
a proactive job renews it weekly.

---

## Database schema

```sql
-- No new tables. Dedup is in-memory (TTLCache).
-- If cross-restart persistence is needed later:
-- CREATE TABLE webhook_seen_events (
--     source      TEXT NOT NULL,
--     event_id    TEXT NOT NULL,
--     seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
--     PRIMARY KEY (source, event_id)
-- );
```

---

## Implementation sequence

### 86a — Base contracts

1. `ze_communication/webhook.py` — `WebhookPayload`, `WebhookVerifier` ABC
2. Update `InboundChannel` with `supports_push` + `webhook_verifier()` defaults
3. `ze_plugin/webhook.py` — `WebhookHandler` Protocol
4. `ZePlugin.webhook_handlers()` default in `ze_plugin/plugin.py`
5. Re-exports in `ze_sdk/channels.py` and `ze_sdk/__init__.py`

### 86b — Dispatcher + route in ze-api

1. `EventDeduplicator` in `ze_api/webhook.py`
2. `WebhookDispatcher` (channel path + plugin path) in `ze_api/webhook.py`
3. `POST /api/v0/webhooks/{source}` route in `ze_api/api/routes/webhooks.py`
4. Wire `WebhookDispatcher` into `ZeContainer` (collect plugin handlers at startup)
5. `_trigger_messenger` implementation

### 86c — Gmail push integration

1. `GmailWebhookVerifier` in `ze_google/webhook.py`
2. `GmailChannel.supports_push`, `webhook_verifier()`, `register_push()`
3. Update `GmailChannel.__init__` to accept `public_url`
4. Update `MessengerPlugin` to pass `public_url` from settings

### 86d — Gmail push registration + renewal

1. `ze_api/cli.py` — `register_gmail_push` command
2. Proactive job: weekly watch renewal
3. Settings: `gmail_pubsub_topic`

### 86e — Tests + docs

1. Unit tests for `GmailWebhookVerifier` (mock JWT, mock history API)
2. Unit tests for `WebhookDispatcher` — channel path (verify → parse → dedup → trigger)
3. Unit tests for `WebhookDispatcher` — plugin path (verify → handle)
4. Update `specs/README.md`

---

## Success criteria

- `POST /api/v0/webhooks/email` with a valid Google OIDC JWT returns `200 {"ok": true}`
- An invalid JWT returns `401`
- An unknown source returns `404`
- A plugin `WebhookHandler` registered via `webhook_handlers()` receives and handles its payload
- A new inbox message triggers `MessengerAgent` within 5 seconds of arrival
- `GmailChannel.supports_push` is `False` when `PUBLIC_URL` is unset (polling fallback)
- `make test-api` passes; no regressions in email send/read tools
- `make lint` clean

---

## Open questions

- [ ] Agent trigger path for plugin handlers: plugins call `container.invoke()` themselves
  inside `handle()`, or does the dispatcher expose a callback? Recommend: plugins own their
  trigger — they know which agent and what context to build.
- [ ] Should inbound messages from unknown senders auto-create a contact proposal?
  Likely yes — defer to implementation of 86c.
- [ ] Cloud Pub/Sub setup: document in `docs/deployment.md`; out of scope for this spec.
