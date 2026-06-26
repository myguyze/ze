# Phase 86 — Webhook Infrastructure

**Status:** Pending
**Depends on:** Phase 85 (Ze Messaging Hub)
**Packages touched:** `core/ze-communication`, `apps/ze-api`, `integrations/ze-google`

---

## What this is

Phase 83 defines `InboundChannel` with `supports_push = False` and a polling fallback.
This phase adds the push path: a generic webhook endpoint in `ze-api`, per-channel
signature verification, a dispatcher that routes payloads to the correct `InboundChannel`,
and Gmail push registration (Google Cloud Pub/Sub → Cloud Push → Ze webhook).

When `GmailChannel.supports_push` returns `True`, the proactive inbound-poll job skips
Gmail entirely — messages arrive in real time instead.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Endpoint shape | `POST /api/v0/webhooks/{channel_type}` | One route per channel type; channel_type disambiguates handler |
| Auth | Per-channel verifier, not `require_api_key` | Webhook callers (Google, etc.) use their own signing schemes, not our bearer token |
| Verifier contract | `WebhookVerifier` Protocol in `ze-communication` | Keeps verification logic with the channel implementation, not in ze-api routing |
| Dispatcher | `WebhookDispatcher` in `ze-api` | Owns routing from raw request → verifier → channel handler → agent trigger |
| Agent trigger | Fire `MessengerAgent` via `container.invoke()` | Reuses the existing LangGraph invocation path; no new queue needed |
| Gmail push mechanism | Google Cloud Pub/Sub + Push subscription | Gmail's official push API; subscription POSTs a base64 JSON envelope to our endpoint |
| Webhook secret storage | `.env` / `ZeApiSettings` | One secret per channel; never in YAML |
| Replay / dedup | `message_id` dedup in `WebhookDispatcher` | Gmail may deliver duplicates; idempotency key = `message_id` |

---

## `core/ze-communication`: webhook verifier contract

```python
# ze_communication/webhook.py

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class WebhookPayload:
    channel_type: str          # matches ChannelType value
    raw_body: bytes
    headers: dict[str, str]


class WebhookVerifier(ABC):
    """Implemented by each channel that supports push delivery."""

    @abstractmethod
    def verify(self, payload: WebhookPayload) -> bool:
        """Return True if the payload is authentic. Raise or return False otherwise."""
        ...

    @abstractmethod
    async def parse(self, payload: WebhookPayload) -> list["InboundMessage"]:
        """Parse a verified webhook payload into zero or more InboundMessages."""
        ...
```

`InboundChannel` grows an optional method:

```python
class InboundChannel(Channel):
    @property
    def supports_push(self) -> bool:
        return False

    def webhook_verifier(self) -> "WebhookVerifier | None":
        """Return verifier if supports_push is True, else None."""
        return None

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
```

---

## `integrations/ze-google`: Gmail push support

### How Gmail push works

1. You create a Google Cloud Pub/Sub topic.
2. You create a Push subscription on that topic pointing to `{PUBLIC_URL}/api/v0/webhooks/email`.
3. You call `gmail.users().watch(userId="me", body={topicName: ..., labelIds: ["INBOX"]})` to subscribe.
4. Gmail posts a `{"message": {"data": "<base64>", "messageId": "..."}}` envelope to your endpoint whenever the inbox changes.
5. The `data` field decodes to `{"emailAddress": "...", "historyId": "..."}`.
6. You call `gmail.users().history().list(startHistoryId=...)` to fetch what changed.
7. Respond `200 OK` within 10s or Google retries.

### GmailWebhookVerifier

Google authenticates push subscriptions via a bearer token included in the `Authorization`
header of the POST. The token is a Google-signed OIDC JWT with audience set to your
webhook URL. Verification: decode JWT, verify signature against Google's public keys,
check `aud` matches `PUBLIC_URL/api/v0/webhooks/email`.

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
        """One-time call to activate Gmail push. Needs a Cloud Pub/Sub topic ARN."""
        service = self._creds.gmail()
        await asyncio.to_thread(
            lambda: service.users().watch(
                userId="me",
                body={"topicName": topic_name, "labelIds": ["INBOX"]},
            ).execute()
        )
```

---

## `apps/ze-api`: webhook endpoint + dispatcher

### Route

```python
# ze_api/api/routes/webhooks.py

@router.post(
    "/webhooks/{channel_type}",
    status_code=200,
    summary="Receive inbound webhook from external channel",
    description="Authenticated by the channel's own signing scheme, not the Ze API key.",
    operation_id="receive_webhook",
)
async def receive_webhook(
    channel_type: str,
    request: Request,
    dispatcher: WebhookDispatcher = Depends(get_webhook_dispatcher),
) -> dict:
    raw_body = await request.body()
    headers = dict(request.headers)
    await dispatcher.dispatch(channel_type, raw_body, headers)
    return {"ok": True}
```

### WebhookDispatcher

```python
# ze_api/webhook.py

class WebhookDispatcher:
    def __init__(
        self,
        registry: ChannelRegistry,
        container: ZeContainer,
        seen_ids: MessageDeduplicator,
    ) -> None: ...

    async def dispatch(
        self, channel_type: str, raw_body: bytes, headers: dict[str, str]
    ) -> None:
        channel = registry.get_inbound(ChannelType(channel_type))
        if channel is None or not channel.supports_push:
            raise WebhookChannelNotFoundError(channel_type)

        verifier = channel.webhook_verifier()
        payload = WebhookPayload(channel_type=channel_type, raw_body=raw_body, headers=headers)
        if not verifier.verify(payload):
            raise WebhookAuthError(channel_type)

        messages = await verifier.parse(payload)
        for msg in messages:
            if seen_ids.is_duplicate(msg.message_id):
                continue
            seen_ids.mark_seen(msg.message_id)
            asyncio.create_task(self._trigger_agent(msg))

    async def _trigger_agent(self, msg: InboundMessage) -> None:
        # Build a synthetic AgentContext and invoke MessengerAgent
        # (or use the orchestration graph to route naturally)
        ...
```

### MessageDeduplicator

In-memory LRU cache of recently seen `message_id` values (capped at 10 000 entries,
TTL 24h). Protects against Google's at-least-once delivery guarantee. A simple
`functools.lru_cache` or `cachetools.TTLCache` is sufficient — no DB needed.

---

## Settings

```python
# ze_api/settings.py additions

gmail_pubsub_topic: str | None = None   # e.g. "projects/my-project/topics/ze-gmail"
```

`PUBLIC_URL` is already in settings; passed to `GmailChannel` at construction time to
enable push mode.

---

## Gmail push registration command

A one-time CLI command (or admin route) to activate watch:

```bash
python -m ze_api.cli register_gmail_push
```

This calls `GmailChannel.register_push(topic_name)`. Gmail watch expires after 7 days;
a proactive job renews it weekly.

---

## Inbound-poll job changes

The existing proactive inbound-poll job (if any) checks `channel.supports_push`:

```python
for channel in registry.inbound_channels():
    if channel.supports_push:
        continue  # messages arrive via webhook
    new_msgs = await channel.poll_new_messages(since=last_checked)
    ...
```

This means Phase 84 is fully backward-compatible: channels without push configured
continue to poll; channels with push configured stop being polled.

---

## Database schema

```sql
-- No new tables. Dedup is in-memory (TTLCache).
-- If persistence across restarts is needed later, add:
-- CREATE TABLE webhook_seen_messages (
--     message_id TEXT PRIMARY KEY,
--     channel_type TEXT NOT NULL,
--     seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
```

---

## Implementation sequence

### 84a — Contract additions in ze-communication

1. `ze_communication/webhook.py` — `WebhookPayload`, `WebhookVerifier` ABC
2. Update `InboundChannel` with `webhook_verifier()` default
3. Update `ze_sdk/channels.py` re-exports to include `WebhookPayload`, `WebhookVerifier`

### 84b — GmailChannel push support

1. `GmailWebhookVerifier` in `ze_google/webhook.py`
2. `GmailChannel.supports_push`, `webhook_verifier()`, `register_push()`
3. Update `GmailChannel.__init__` to accept `public_url`
4. Update `MessengerPlugin` to pass `public_url` from settings

### 84c — ze-api dispatcher + route

1. `WebhookDispatcher` + `MessageDeduplicator` in `ze_api/webhook.py`
2. `POST /api/v0/webhooks/{channel_type}` route
3. Wire `WebhookDispatcher` into `ZeContainer`
4. `_trigger_agent` implementation (route inbound message to MessengerAgent)

### 84d — Gmail push registration + renewal

1. `ze_api/cli.py` — `register_gmail_push` command
2. Proactive job: weekly watch renewal
3. Settings: `gmail_pubsub_topic`

### 84e — Tests + docs

1. Unit tests for `GmailWebhookVerifier` (mock JWT, mock history API)
2. Unit tests for `WebhookDispatcher` (verify → parse → dedup → trigger)
3. Update `specs/README.md`

---

## Success criteria

- `POST /api/v0/webhooks/email` with a valid Google OIDC JWT returns `200 {"ok": true}`
- An invalid JWT returns `401`
- A new inbox message triggers `MessengerAgent` within 5 seconds of arrival
- `make test-api` passes; no regressions in email send/read tools
- `GmailChannel.supports_push` is `False` when `PUBLIC_URL` is unset (polling fallback)
- `make lint` clean

---

## Open questions

- [ ] Agent trigger path: invoke `MessengerAgent` directly, or route through the LangGraph
  orchestration graph so the full routing/memory/telemetry pipeline runs?
  Recommendation: use `container.invoke()` with a synthetic session so memory writes and
  cost tracking apply. Defer to implementation.
- [ ] Should inbound messages from unknown senders auto-create a contact proposal (same
  as the email agent does today via `extract_email_contacts`)? Likely yes — defer to
  implementation.
- [ ] Cloud Pub/Sub setup: document in `docs/deployment.md`; out of scope for this spec.
