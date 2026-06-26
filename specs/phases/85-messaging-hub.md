# Phase 85 — Ze Messaging Hub

**Status:** Done
**Depends on:** Phase 83 (ze-communication + ze-messenger)
**Supersedes:** Phase 84a draft (absorbed into this spec)
**Packages touched:** `core/ze-communication`, `integrations/ze-google`, `plugins/ze-messenger`,
  `plugins/ze-personal`, `apps/ze-api`

---

## What this is

Ze should be connectable to the user's actual communication channels — multiple Gmail accounts
(ProtonMail, WhatsApp, etc. are architecturally supported but not implemented here) — and treat
them as a first-class part of the assistant system, not just as output channels for sending email.

Right now:
- `MessengerAgent` is a renamed `EmailAgent`. Tools are typed to `GoogleCredentials`/`GmailChannel`
  directly, bypassing `ChannelRegistry`. There is no concept of "which of Ze's accounts to use".
- `poll_new_messages` and `ChannelRegistry.inbound_channels()` are dead code. Nothing calls them.
- Inbound messages contribute nothing to memory, signals, or the correlation engine.
- There is no concept of the user's own channels — which inboxes Ze monitors is implicit from
  which OAuth token was configured. Two Gmail accounts would collide in the registry.

This phase makes Ze a proper messaging hub:

1. **UserChannel model** — explicit store of which channels Ze is connected to, with handles,
   display names, outbound defaults, and poll toggles. Supports multiple instances per type.
2. **InboundChannel identity** — `channel_id` string per instance (e.g. `"gmail:joao@gmail.com"`)
   so the registry can hold two Gmail accounts without collision.
3. **Inbound polling pipeline** — `InboundPollingJob` polls all enabled channels, watermarks
   per instance, and processes each message through memory + signals.
4. **Message intelligence** — inbound messages write episodes, extract facts, and emit signals
   to the correlation engine.
5. **Thread-aware outbound routing** — `send_email` resolves which of Ze's accounts to use:
   existing thread → same account that received/sent it; no thread → default outbound account.
   The mapping is built automatically from inbound polls and sent messages — no manual config.
6. **Channel REST API** — visibility into which channels are connected and their poll state.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| UserChannel storage | `user_channels` table in ze-personal | Personal domain owns user identity/config; contacts already there |
| Channel identity | `channel_id: str` on `InboundChannel` (e.g. `"gmail:joao@gmail.com"`) | Unique per instance, not per type — prerequisite for multi-account without registry redesign |
| Registry outbound index | Unchanged (`ChannelType → Channel`, last registered wins) | Used for non-routed access; per-thread routing goes through secondary inbound index |
| Registry inbound index | Secondary `dict[channel_id, InboundChannel]` | Enables `get_inbound_by_id` for routing and per-channel poll |
| Thread routing data | `thread_channel_map(thread_id, channel_id)` in ze-personal | Built automatically; persisted so routing survives restarts |
| Thread routing location | Resolved in `send_email` tool, not in agent pre-loop | Tool is where `thread_id` is known — agent can't always know it before the loop runs |
| Routing priority | ThreadChannelMap → default outbound | Prefers continuity; contact-handle matching deferred (needs more data model work) |
| `send_email` channel abstraction | Routes through `channel.send()`, not direct Gmail API | Tool is no longer credentials-coupled; works for any channel implementation |
| `list_emails` / `get_email` | Continue via credentials dep from agent's default-channel resolution | Gmail-specific search/fetch doesn't map cleanly to `Channel` ABC; abstract in a later phase |
| Signal integration | `MessagingSignalSource` pushes `Signal` objects per inbound message | Existing admission gate handles dedup via `external_ref = message_id`; no new tables needed |
| Notification on inbound | Known contact → push; unknown sender → episode only (no alert) | Avoids notification spam from newsletters/automated mail |
| Watermark | `user_channel_watermarks(channel_id, last_polled_at)` in ze-personal | Same package as UserChannel; one row per instance |
| Memory writes | Episode per message; facts via existing `propose_facts` LLM pass (async, non-blocking) | Same path as conversation memory; agent = "messenger", source = "inbound" |
| `poll_new_messages` vs. `supports_push` | Job skips channels where `supports_push = True` (reserved for Phase 86 webhooks) | Clean seam; Phase 86 delivers real-time push without touching the job |

---

## `core/ze-communication`: channel identity + InboundMessage headers

Add `headers: dict[str, str]` field to `InboundMessage` (default empty dict). Channel
implementations populate it with transport-level headers (`List-Unsubscribe`, `Precedence`,
`X-Mailer`, etc.) so `InboundMessageProcessor` can classify automated senders without an
LLM call. Non-email channels leave it empty.

Add `channel_id` property to `InboundChannel`. Default returns `channel_type.value` so
existing single-account deployments need no changes:

```python
# ze_communication/channel.py

class InboundChannel(Channel):

    @property
    def channel_id(self) -> str:
        """Unique identifier for this channel instance.

        Override in multi-account scenarios (e.g. "gmail:joao@gmail.com").
        Default is the channel type value — correct when only one instance
        of this type is registered.
        """
        return self.channel_type.value

    @property
    def supports_push(self) -> bool:
        return False

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
```

Update `ChannelRegistry` to maintain the secondary inbound index:

```python
# ze_communication/registry.py

class ChannelRegistry:
    def __init__(self, channels: list[Channel]) -> None:
        self._channels: dict[ChannelType, Channel] = {c.channel_type: c for c in channels}
        self._inbound: dict[str, InboundChannel] = {
            c.channel_id: c
            for c in channels
            if isinstance(c, InboundChannel)
        }

    def get(self, channel_type: ChannelType) -> Channel: ...         # unchanged
    def get_inbound(self, channel_type: ChannelType) -> InboundChannel | None: ...  # unchanged
    def available(self) -> list[ChannelType]: ...                    # unchanged

    def inbound_channels(self) -> list[InboundChannel]:
        """All registered inbound instances (all accounts, all types)."""
        return list(self._inbound.values())

    def get_inbound_by_id(self, channel_id: str) -> InboundChannel | None:
        return self._inbound.get(channel_id)
```

---

## `integrations/ze-google`: GmailChannel identity

```python
# ze_google/gmail_channel.py

class GmailChannel(InboundChannel):

    @property
    def channel_id(self) -> str:
        # Stable after first poll or get_thread (both call _resolve_user_email).
        # Falls back to "email" until resolved — the polling job resolves before
        # writing the watermark row, so the DB always gets the stable key.
        if self._user_email:
            return f"gmail:{self._user_email}"
        return self.channel_type.value
```

---

## `plugins/ze-personal`: UserChannel + watermark + thread routing stores

### Migration (continues zc chain)

```sql
-- zc_NNN_user_channels.py

CREATE TABLE user_channels (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id        TEXT        NOT NULL UNIQUE,   -- matches InboundChannel.channel_id
    channel_type      TEXT        NOT NULL,
    handle            TEXT        NOT NULL,           -- user's address on this channel
    display_name      TEXT,                           -- "Personal Gmail", "Work Gmail"
    is_default_outbound BOOLEAN   NOT NULL DEFAULT FALSE,
    poll_enabled      BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_channel_watermarks (
    channel_id        TEXT        PRIMARY KEY REFERENCES user_channels(channel_id),
    last_polled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE thread_channel_map (
    thread_id         TEXT        PRIMARY KEY,
    channel_id        TEXT        NOT NULL,   -- which of Ze's accounts owns this thread
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

One default outbound per channel type is enforced at the application layer.

### Types

```python
# ze_personal/channels/types.py

from dataclasses import dataclass
from datetime import datetime


@dataclass
class UserChannel:
    id: str
    channel_id: str          # matches InboundChannel.channel_id
    channel_type: str        # ChannelType value
    handle: str              # user's address
    display_name: str | None
    is_default_outbound: bool
    poll_enabled: bool
    created_at: datetime
```

### UserChannelStore

```python
# ze_personal/channels/user_channel_store.py

class UserChannelStore:
    async def upsert(self, channel: UserChannel) -> None:
        """Insert or update (keyed by channel_id)."""
        ...

    async def list_all(self) -> list[UserChannel]: ...

    async def get_default_outbound(self, channel_type: str) -> UserChannel | None: ...

    async def set_default_outbound(self, channel_id: str) -> None:
        """Set default outbound; clears the flag on others of same type in a transaction."""
        ...

    async def set_poll_enabled(self, channel_id: str, enabled: bool) -> None: ...
```

### ChannelWatermarkStore

```python
# ze_personal/channels/watermark_store.py

class ChannelWatermarkStore:
    DEFAULT_LOOKBACK_HOURS = 24

    async def get(self, channel_id: str) -> datetime:
        """Returns last polled time, or 24 h ago if never polled."""
        ...

    async def set(self, channel_id: str, polled_at: datetime) -> None:
        """Upsert watermark (INSERT ... ON CONFLICT DO UPDATE)."""
        ...
```

### ThreadChannelMap

```python
# ze_personal/channels/thread_channel_map.py

class ThreadChannelMap:
    async def get(self, thread_id: str) -> str | None:
        """Return channel_id that owns this thread, or None if unknown."""
        async with self._pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT channel_id FROM thread_channel_map WHERE thread_id=$1", thread_id
            )

    async def set(self, thread_id: str, channel_id: str) -> None:
        """Upsert thread → channel mapping."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO thread_channel_map (thread_id, channel_id, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (thread_id) DO UPDATE
                    SET channel_id = EXCLUDED.channel_id,
                        updated_at = NOW()
                """,
                thread_id, channel_id,
            )
```

### ContactChannelStore: add find_by_handle

```python
# ze_personal/contacts/channel_store.py  (addition)

async def find_by_handle(
    self, channel_type: ChannelType, handle: str
) -> Contact | None:
    async with self._pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.id, c.name
            FROM contact_channels ch
            JOIN contacts c ON c.id = ch.contact_id
            WHERE ch.channel_type = $1 AND ch.handle = $2
            LIMIT 1
            """,
            channel_type, handle,
        )
    return Contact(id=row["id"], name=row["name"]) if row else None
```

No migration — uses existing `contact_channels` table.

---

## `plugins/ze-messenger`: InboundPollingJob

```python
# ze_messenger/jobs/inbound_poll.py

class InboundPollingJob(ProactiveJob):
    name = "inbound_poll"

    def __init__(
        self,
        registry: ChannelRegistry,
        watermark_store: ChannelWatermarkStore,
        user_channel_store: UserChannelStore,
        processor: "InboundMessageProcessor",
    ) -> None: ...

    async def run(self) -> None:
        enabled = {uc.channel_id for uc in await self._user_channels.list_all()
                   if uc.poll_enabled}
        for channel in self._registry.inbound_channels():
            if channel.channel_id not in enabled:
                continue
            if channel.supports_push:
                continue  # Phase 86 handles these via webhook
            await self._poll(channel)

    async def _poll(self, channel: InboundChannel) -> None:
        # Force channel_id resolution before watermark lookup
        if hasattr(channel, '_resolve_user_email'):
            await channel._resolve_user_email()

        since = await self._watermarks.get(channel.channel_id)
        try:
            messages = await channel.poll_new_messages(since=since)
        except Exception:
            self._log.warning("inbound_poll_failed", channel_id=channel.channel_id)
            return

        if not messages:
            return

        for msg in messages:
            await self._processor.process(msg, channel_id=channel.channel_id)

        await self._watermarks.set(channel.channel_id, datetime.now(timezone.utc))
        # Auto-register channel in user_channels on first successful poll
        await self._user_channels.upsert(UserChannel(
            id=str(uuid4()),
            channel_id=channel.channel_id,
            channel_type=channel.channel_type.value,
            handle=getattr(channel, '_user_email', None) or channel.channel_id,
            display_name=None,
            is_default_outbound=False,
            poll_enabled=True,
            created_at=datetime.now(timezone.utc),
        ))
```

---

## `plugins/ze-messenger`: InboundMessageProcessor

Implements the memory contribution policy defined in [`arch/communication-hub.md`](../../arch/communication-hub.md).
Sender classification gates which memory paths activate — see that document for rationale.

```python
# ze_messenger/inbound/processor.py

class SenderClass(StrEnum):
    KNOWN_CONTACT = "known_contact"
    REPLIED_TO    = "replied_to"
    UNKNOWN_HUMAN = "unknown_human"
    AUTOMATED     = "automated"


class InboundMessageProcessor:
    """Processes a single inbound message through the full Ze pipeline."""

    def __init__(
        self,
        memory_store: MemoryStore,
        contact_channel_store: ContactChannelStore,
        thread_channel_map: ThreadChannelMap,
        notifier: ProactiveNotifier,
        signal_source: "MessagingSignalSource",
        llm_client: LLMClient,
        automated_sender_patterns: list[str],   # from config
    ) -> None: ...

    async def process(self, msg: InboundMessage, channel_id: str) -> None:
        sender_class = await self._classify(msg)

        if sender_class == SenderClass.AUTOMATED:
            return  # nothing written

        # 1. Thread → channel mapping (enables reply routing)
        if msg.thread_id:
            await self._thread_map.set(msg.thread_id, channel_id)

        # 2. Episode write — always for non-automated senders
        await self._memory.write_episode(
            source="inbound_message",
            agent="messenger",
            prompt=(
                f"[Inbound {msg.channel_type} from {msg.sender}]"
                + (f" Subject: {msg.subject}" if msg.subject else "")
            ),
            response=msg.body,
            metadata={
                "channel_id": channel_id,
                "channel_type": msg.channel_type,
                "message_id": msg.message_id,
                "sender": msg.sender,
                "sender_class": sender_class,
                "thread_id": msg.thread_id,
                "received_at": msg.received_at.isoformat(),
            },
        )

        significant = sender_class in (SenderClass.KNOWN_CONTACT, SenderClass.REPLIED_TO)

        # 3. Signal + notification only for significant senders
        if significant:
            self._signals.push(msg)

            known = await self._contacts.find_by_handle(
                channel_type=msg.channel_type, handle=msg.sender
            )
            if known:
                subject_part = f": {msg.subject}" if msg.subject else ""
                await self._notifier.push(
                    title=f"Message from {known.name or msg.sender}{subject_part}",
                    body=msg.body[:200],
                    tags=["message", msg.channel_type],
                )

        # 4. Async fact pass only for significant senders
        if significant:
            asyncio.create_task(self._extract_facts(msg))

    async def _classify(self, msg: InboundMessage) -> SenderClass:
        if _is_automated(msg.sender, msg.headers, self._automated_patterns):
            return SenderClass.AUTOMATED
        known = await self._contacts.find_by_handle(msg.channel_type, msg.sender)
        if known:
            return SenderClass.KNOWN_CONTACT
        if msg.thread_id and await self._thread_map.get(msg.thread_id):
            return SenderClass.REPLIED_TO
        return SenderClass.UNKNOWN_HUMAN

    async def _extract_facts(self, msg: InboundMessage) -> None:
        """Non-fatal — episode is already written before this runs."""
        ...
```

---

## `plugins/ze-messenger`: MessagingSignalSource

```python
# ze_messenger/signals.py

from ze_plugin.signals import SignalSource
from ze_communication.types import InboundMessage
from ze_memory.types import Signal, EntityRef
from uuid import uuid4


class MessagingSignalSource(SignalSource):
    source_key = "messaging"

    def __init__(self) -> None:
        self._buffer: list[Signal] = []

    def push(self, msg: InboundMessage) -> None:
        """Called by InboundMessageProcessor after each inbound message."""
        self._buffer.append(Signal(
            id=uuid4(),
            source=self.source_key,
            external_ref=msg.message_id,  # dedup key; admission gate skips duplicates
            title=msg.subject or f"Message from {msg.sender}",
            summary=msg.body[:500],
            occurred_at=msg.received_at,
            entities=[EntityRef(name=msg.sender, entity_type="person")],
            magnitude=0.0,
            payload={
                "channel_type": msg.channel_type,
                "thread_id": msg.thread_id,
                "sender": msg.sender,
            },
        ))

    async def poll(self, since: datetime) -> list[Signal]:
        """Drain buffer — push-then-poll pattern, same as NewsSignalSource."""
        signals, self._buffer = self._buffer, []
        return signals
```

`MessengerPlugin.signal_sources()` returns `[self._messaging_signal_source]`.
The admission gate's `external_ref` dedup ensures restarting the poll job never
double-inserts a message signal.

---

## `plugins/ze-messenger`: MessengerAgent — outbound routing

The agent resolves the default channel for the turn (used for `list_emails` and other
Gmail-specific tools that need credentials). Thread-aware routing for `send_email` is
handled in the tool itself, where the `thread_id` is known.

```python
# ze_messenger/agents/messenger/agent.py

class MessengerAgent(BaseAgent):

    def __init__(
        self,
        openrouter_client: LLMClient,
        channel_registry: ChannelRegistry,
        user_channel_store: UserChannelStore,
        thread_channel_map: ThreadChannelMap,
        settings: Settings,
    ) -> None:
        self._client = openrouter_client
        self._registry = channel_registry
        self._user_channels = user_channel_store
        self._thread_map = thread_channel_map
        self._settings = settings

    async def run(self, ctx: AgentContext) -> AgentResult:
        # Resolve default channel for this turn (used for list/get/archive tools)
        default_channel = await self._default_channel()

        deps: dict = {
            "channel_registry": self._registry,
            "thread_channel_map": self._thread_map,
            "user_channel_store": self._user_channels,
        }
        if default_channel and hasattr(default_channel, '_creds'):
            # Inject credentials for Gmail-specific list/get/archive tools
            deps["credentials"] = default_channel._creds

        response, loop_tool_calls = await self.agentic_loop(
            ctx, client=self._client, messages=list(ctx.messages),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
            deps=deps,
        )
        ...

    async def _default_channel(self) -> InboundChannel | None:
        uc = await self._user_channels.get_default_outbound("email")
        if uc:
            return self._registry.get_inbound_by_id(uc.channel_id)
        channels = [c for c in self._registry.inbound_channels()
                    if c.channel_type.value == "email"]
        return channels[0] if channels else None
```

### `send_email` tool: thread-aware routing

This is where routing is actually decided. The tool has `thread_id` and can resolve
the right channel:

```python
@tool(access=ToolAccess.WRITE, description="Send an email or reply to a thread.")
async def send_email(
    channel_registry: ChannelRegistry,
    thread_channel_map: ThreadChannelMap,
    user_channel_store: UserChannelStore,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict:
    channel = await _resolve_send_channel(
        channel_registry, thread_channel_map, user_channel_store, thread_id
    )

    msg = Message(
        channel_type=ChannelType.EMAIL,
        to=to,
        subject=subject,
        body=body,
        thread_id=thread_id,
    )
    sent = await channel.send(msg)

    # Record the mapping so future replies on this thread use the same account
    if sent.thread_id:
        await thread_channel_map.set(sent.thread_id, channel.channel_id)

    return {
        "message_id": sent.message_id,
        "thread_id": sent.thread_id,
        "sent_from": channel.channel_id,
    }


async def _resolve_send_channel(
    registry: ChannelRegistry,
    thread_map: ThreadChannelMap,
    user_channels: UserChannelStore,
    thread_id: str | None,
) -> InboundChannel:
    # 1. Thread known → use the account that owns it
    if thread_id:
        channel_id = await thread_map.get(thread_id)
        if channel_id:
            channel = registry.get_inbound_by_id(channel_id)
            if channel is not None:
                return channel

    # 2. Default outbound
    uc = await user_channels.get_default_outbound("email")
    if uc:
        channel = registry.get_inbound_by_id(uc.channel_id)
        if channel is not None:
            return channel

    # 3. Any available email channel
    for channel in registry.inbound_channels():
        if channel.channel_type.value == "email":
            return channel

    raise ChannelNotFoundError("No email channel available")
```

`list_emails`, `get_email`, and `archive_email` continue using the `credentials` dep
injected by the agent from the default channel. They are Gmail-specific tools; abstracting
them through `Channel` is deferred to when a second email provider is wired.

---

## `apps/ze-api`: channel REST API

```python
# ze_api/api/routes/channels.py

router = APIRouter(prefix="/api/v0/channels", tags=["channels"])


@router.get(
    "",
    response_model=ChannelListResponse,
    summary="List connected communication channels",
    description="Returns channels Ze is connected to with poll state and last poll time.",
    operation_id="list_channels",
)
async def list_channels(_: str = Depends(require_api_key), ...) -> ChannelListResponse:
    channels = await user_channel_store.list_all()
    registry_channels = {c.channel_id: c for c in channel_registry.inbound_channels()}
    watermarks = {uc.channel_id: await watermark_store.get(uc.channel_id) for uc in channels}
    return ChannelListResponse(channels=[
        ChannelInfo(
            channel_id=uc.channel_id,
            channel_type=uc.channel_type,
            handle=uc.handle,
            display_name=uc.display_name,
            is_default_outbound=uc.is_default_outbound,
            poll_enabled=uc.poll_enabled,
            supports_push=registry_channels[uc.channel_id].supports_push
                          if uc.channel_id in registry_channels else False,
            last_polled_at=watermarks.get(uc.channel_id),
        )
        for uc in channels
    ])


@router.patch(
    "/{channel_id}",
    response_model=ChannelResponse,
    summary="Update channel configuration",
    description="Toggle poll_enabled or set as default outbound.",
    operation_id="update_channel",
)
async def update_channel(
    channel_id: str,
    body: ChannelUpdateRequest,
    _: str = Depends(require_api_key),
    ...
) -> ChannelResponse:
    if body.poll_enabled is not None:
        await user_channel_store.set_poll_enabled(channel_id, body.poll_enabled)
    if body.is_default_outbound:
        await user_channel_store.set_default_outbound(channel_id)
    if body.display_name is not None:
        await user_channel_store.set_display_name(channel_id, body.display_name)
    ...
```

```python
# ze_api/api/schemas.py  (additions)

@dataclass
class ChannelInfo:
    channel_id: str
    channel_type: str
    handle: str
    display_name: str | None
    is_default_outbound: bool
    poll_enabled: bool
    supports_push: bool
    last_polled_at: datetime | None

@dataclass
class ChannelListResponse:
    channels: list[ChannelInfo]

@dataclass
class ChannelUpdateRequest:
    poll_enabled: bool | None = None
    is_default_outbound: bool | None = None
    display_name: str | None = None

@dataclass
class ChannelResponse:
    channel: ChannelInfo
```

Sample `GET /api/v0/channels` response:

```json
{
  "channels": [
    {
      "channel_id": "gmail:joao@gmail.com",
      "channel_type": "email",
      "handle": "joao@gmail.com",
      "display_name": "Personal Gmail",
      "is_default_outbound": true,
      "poll_enabled": true,
      "supports_push": false,
      "last_polled_at": "2026-06-26T14:00:00Z"
    }
  ]
}
```

---

## `config/config.yaml`: poll interval

```yaml
proactive:
  inbound_poll_interval_seconds: 300   # 5 min default; use 60 for local dev
```

---

## Memory contribution policy

See [`arch/communication-hub.md`](../../arch/communication-hub.md) — "Memory contribution policy"
and "Signal policy" sections. This phase implements that policy via `SenderClass` classification
in `InboundMessageProcessor`. The summary:

- Automated senders → nothing written
- Unknown human senders → episode only (searchable, no LLM pass, no signal)
- Known contacts and replied-to threads → episode + async fact pass + signal + notification

The `sender_class` field in episode metadata allows future consolidation logic to distinguish
messaging episodes from conversation episodes (they share `agent="messenger"` but different sources).

`send_email` writes `thread_id → channel_id` to `ThreadChannelMap` after every successful send,
which gates the "replied-to" class for subsequent inbound messages in the same thread.

---

## Phase sequencing note

| Phase | What |
|---|---|
| 83 | ze-communication + ze-messenger — channel contract, GmailChannel as InboundChannel ✅ |
| **85** | **This phase — full inbound pipeline, channel config, thread-aware routing, signal integration** |
| 86 | Webhooks — `supports_push = True`, `POST /api/v0/webhooks/{channel_type}`, Gmail Pub/Sub |

---

## Implementation sequence

### 85a — Channel identity + registry (ze-communication, ze-google)

1. Add `channel_id` property to `InboundChannel` in `ze-communication`
2. Update `ChannelRegistry` with `_inbound` secondary index and `get_inbound_by_id()`
3. Override `channel_id` in `GmailChannel` (lazy resolution from `_user_email`)
4. Update tests in `ze-communication` and `ze-google`

### 85b — User channel + thread routing stores (ze-personal)

1. Write migration (`user_channels`, `user_channel_watermarks`, `thread_channel_map` tables)
2. Write `UserChannelStore`, `ChannelWatermarkStore`, `ThreadChannelMap`
3. Add `find_by_handle` to `ContactChannelStore`
4. Wire stores into `PersonalPlugin.agent_deps()` and `ZeContainer`

### 85c — Inbound pipeline (ze-messenger)

1. Write `MessagingSignalSource`; wire into `MessengerPlugin.signal_sources()`
2. Write `InboundMessageProcessor` (episode + thread_map + signal + notification)
3. Write `InboundPollingJob`; wire into `MessengerPlugin.register_proactive_jobs()`
4. Wire `ChannelWatermarkStore`, `UserChannelStore`, `ThreadChannelMap` into job + processor deps

### 85d — MessengerAgent + send_email routing (ze-messenger)

1. Update `MessengerAgent.__init__` to accept `channel_registry`, `user_channel_store`,
   `thread_channel_map` (drop direct `google_credentials` dep)
2. Implement `_default_channel()` resolution
3. Update `send_email` tool to route through `_resolve_send_channel` + `channel.send()`
4. Update `MessengerPlugin.agent_deps()` to inject new deps

### 85e — REST API (ze-api)

1. Write `ze_api/api/routes/channels.py`
2. Add schemas to `ze_api/api/schemas.py`
3. Register route in `ze_api/api/app.py`
4. Expose `user_channel_store`, `watermark_store`, `thread_channel_map` on `ZeContainer`

### 85f — Tests + cleanup

1. `test_thread_channel_map.py` — get/set, upsert semantics
2. `test_inbound_message_processor.py` — thread_map populated; episode written; signal pushed; notification on known contact
3. `test_inbound_polling_job.py` — mock registry + stores; assert processor called per message
4. `test_messaging_signal_source.py` — push + poll drains buffer; dedup via external_ref
5. `test_user_channel_store.py` — upsert, list, default outbound toggle (clears others)
6. `test_send_email_routing.py` — thread_id present → uses mapped channel; no thread_id → default; writes mapping after send
7. `test_channels_route.py` — GET list, PATCH poll_enabled, PATCH default
8. Update `specs/README.md`; update `CLAUDE.md` dep graph + phase table

---

## Success criteria

- `InboundPollingJob` iterates all poll-enabled channels from `UserChannelStore`; skips `supports_push` channels
- Each polled message: writes episode, sets `thread_channel_map[thread_id] = channel_id`, emits signal
- Known contact sender triggers push notification; unknown sender does not
- `send_email` with an existing `thread_id` uses the channel that originally received/sent that thread
- `send_email` with no `thread_id` uses the default outbound channel
- After `send_email`, the sent `thread_id` is recorded in `thread_channel_map`
- `GmailChannel.channel_id` returns `"gmail:{email}"` after credential resolution
- `ChannelRegistry.get_inbound_by_id("gmail:joao@gmail.com")` returns the channel
- `user_channels` row is upserted automatically after first successful poll
- `GET /api/v0/channels` returns connected channels with `last_polled_at`
- `PATCH /api/v0/channels/{id}` toggles `poll_enabled` and `is_default_outbound`
- `MessagingSignalSource.poll()` returns signals that feed the correlation engine
- `make test-messenger`, `make test-communication`, `make test-personal`, `make test` all pass
