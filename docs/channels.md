# Ze — Communication Channels

Ze connects to the user's communication channels and treats them as first-class
parts of the assistant system — not just output sinks for sending messages.
This document covers the channel abstraction, the inbound pipeline, thread
routing, and how to add a new channel.

For the architectural invariants that all phases must respect, see
[`specs/arch/communication-hub.md`](../specs/arch/communication-hub.md).

---

## Overview

```
ChannelRegistry
  ├── GmailChannel (gmail:joao@gmail.com)   InboundChannel
  ├── GmailChannel (gmail:joao@work.com)    InboundChannel
  └── (future: ProtonMailChannel, WhatsAppChannel, ...)

InboundPollingJob ──polls──▶ InboundMessageProcessor
                                  ├── write episode (ze-memory)
                                  ├── set thread_channel_map
                                  ├── emit signal (MessagingSignalSource)
                                  └── push notification (known contacts only)

send_email tool ──resolves channel via──▶ ThreadChannelMap / UserChannelStore
```

Packages involved:

| Package | Role |
|---|---|
| `core/ze-communication` | `Channel`/`InboundChannel` ABCs, `ChannelRegistry`, `InboundMessage` types |
| `integrations/ze-google` | `GmailChannel` implementation |
| `plugins/ze-messenger` | Polling job, message processor, signal source, `MessengerAgent` |
| `plugins/ze-personal` | `UserChannelStore`, `ChannelWatermarkStore`, `ThreadChannelMap` |
| `apps/ze-api` | `GET/PATCH /api/v0/channels` REST API |

---

## Channel identity

Every channel instance has a stable `channel_id` string of the form
`"{provider}:{handle}"`:

```
gmail:joao@gmail.com
gmail:joao@work.com
proton:joao@protonmail.com
whatsapp:+351912345678
```

`ChannelType` identifies the *protocol* (`email`, `whatsapp`).  
`channel_id` identifies the *instance*. Routing, watermarks, and thread
ownership all key off `channel_id`, never `ChannelType` alone.

`GmailChannel` resolves its `channel_id` lazily — it makes a `getProfile` call
on first use and caches the result. Until resolved it falls back to `"email"`.
The polling job forces resolution before writing the watermark row, so the DB
always gets the stable key.

---

## ABCs

### `Channel` (outbound)

```python
# ze_communication/channel.py
class Channel(ABC):
    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    async def send(self, message: Message) -> SentMessage: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Thread: ...
```

### `InboundChannel`

```python
class InboundChannel(Channel):
    @property
    def channel_id(self) -> str:
        """Override to return "provider:handle" for multi-account scenarios."""
        return self.channel_type.value

    @property
    def supports_push(self) -> bool:
        return False  # Phase 86: set True + implement register_push()

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
```

`InboundMessage` carries transport-level `headers` (populated by the channel
implementation) so the message processor can classify automated senders without
an LLM call.

---

## ChannelRegistry

`ChannelRegistry` holds two indexes:

- `dict[ChannelType, Channel]` — last registered wins per type (for non-routed
  access, e.g. `registry.get(ChannelType.EMAIL)`)
- `dict[channel_id, InboundChannel]` — one entry per instance

```python
registry.inbound_channels()          # all InboundChannel instances
registry.get_inbound_by_id("gmail:joao@gmail.com")  # instance lookup
```

The registry is built in `ZeContainer` after plugins are instantiated (channels
come from `plugin.channels()`) but before agents are bootstrapped (so agents
can receive it via DI).

---

## Inbound polling pipeline

### `InboundPollingJob`

Runs on a cron schedule (default every 5 minutes; configurable via
`proactive.inbound_poll_interval_seconds` in `config.yaml`).

For each registered inbound channel:
1. Skip if `poll_enabled = False` in `user_channels`
2. Skip if `channel.supports_push = True` (Phase 86 handles those via webhook)
3. Read watermark from `user_channel_watermarks` (default: 24 h ago on first run)
4. Call `channel.poll_new_messages(since=watermark)`
5. Pass each message to `InboundMessageProcessor`
6. Update watermark to `now()`
7. Upsert a row in `user_channels` (auto-registers the channel on first poll)

### `InboundMessageProcessor`

Classifies each message and gates which memory paths activate:

| Sender class | Criteria | Episode | Facts | Signal | Notification |
|---|---|---|---|---|---|
| **Known contact** | Handle in `contact_channels` | ✅ | ✅ async | ✅ | ✅ |
| **Replied-to** | Thread in `thread_channel_map` | ✅ | ✅ async | ✅ | ✅ |
| **Unknown human** | Not in contacts, not replied-to | ✅ | ❌ | ❌ | ❌ |
| **Automated** | Matches automated sender patterns | ❌ | ❌ | ❌ | ❌ |

Automated sender detection is header-based (no LLM):
- Address prefixes: `noreply@`, `no-reply@`, `notifications@`, `postmaster@`,
  `mailer-daemon@`, `donotreply@`, `bounce@`
- `List-Unsubscribe` header present
- `Precedence: bulk` or `Precedence: list`
- Configurable extra patterns via `messaging.automated_senders` in `config.yaml`

Episodes are written with `agent="messenger"` so session consolidation excludes
them from conversation grouping.

### `MessagingSignalSource`

Push-then-drain buffer: `InboundMessageProcessor` pushes a `Signal` per
significant message; the correlation engine drains it on each cycle.

`external_ref = message_id` is the dedup key — the admission gate in `ze-memory`
skips signals already seen, so restarting the polling job never double-counts.

---

## Thread ownership and routing

A thread belongs to exactly one of Ze's channel instances — the one that
received or sent the first message in that thread.

**`ThreadChannelMap`** is the single source of truth. It is populated by:
- `InboundMessageProcessor.process()` — for every polled message with a `thread_id`
- `send_email` tool — after every successful send

**Send routing priority** (in `send_email`):
1. Thread known → use its mapped channel
2. No thread or not in map → use `is_default_outbound` channel
3. No default → use any available channel of the right type

### User channel config

`user_channels` stores which of Ze's channels are connected:

| Column | Purpose |
|---|---|
| `channel_id` | Matches `InboundChannel.channel_id` |
| `handle` | User's address on this channel |
| `display_name` | Human label ("Personal Gmail", "Work Gmail") |
| `is_default_outbound` | Used by send routing when no thread context |
| `poll_enabled` | False to pause polling without disconnecting |

One default outbound per channel type is enforced by `UserChannelStore.set_default_outbound()`.

---

## REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/v0/channels` | List connected channels with poll state and last poll time |
| `PATCH` | `/api/v0/channels/{channel_id}` | Toggle `poll_enabled`, set `is_default_outbound`, update `display_name` |

Sample `GET` response:

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

## Adding a new channel

Adding ProtonMail, WhatsApp, Slack, or any other channel only requires work in
a new integration package. No changes to `ze-messenger`, `ze-personal`, or
`ze-api` are needed.

### 1. Create the integration package

```
integrations/ze-proton/
    ze_proton/
        __init__.py
        proton_channel.py
        auth.py           # credentials + ZeIntegration
```

### 2. Implement `InboundChannel`

```python
from ze_communication.channel import InboundChannel
from ze_communication.types import ChannelType, InboundMessage, Message, SentMessage, Thread

class ProtonMailChannel(InboundChannel):

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.EMAIL   # or add a new ChannelType value

    @property
    def channel_id(self) -> str:
        return f"proton:{self._user_email}"

    @property
    def supports_push(self) -> bool:
        return False   # set True when Phase 86 webhook support is ready

    async def send(self, message: Message) -> SentMessage: ...
    async def get_thread(self, thread_id: str) -> Thread: ...

    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]:
        # Return InboundMessage objects with headers populated for
        # automated sender classification (List-Unsubscribe, Precedence, etc.)
        ...
```

**Contract requirements:**

| Method | Requirements |
|---|---|
| `send` | Must return `SentMessage` with non-empty `message_id` and `thread_id`. |
| `get_thread` | Messages sorted by `sent_at` ascending. `is_outbound=True` for Ze's messages. |
| `poll_new_messages` | Return only messages received after `since`. Populate `headers` with transport-level headers. `subject` is `None` for channels that don't have a subject concept. |

Wrap transport exceptions as `ChannelSendError` (from `ze_sdk.errors`) — never
let raw provider errors escape the channel boundary.

### 3. Wire via a plugin

Return the channel instance from a plugin's `channels()` method:

```python
class ProtonPlugin(ZePlugin):
    def __init__(self, proton_credentials: ProtonCredentials | None = None) -> None:
        self._creds = proton_credentials

    def channels(self) -> list:
        if self._creds is None:
            return []
        return [ProtonMailChannel(credentials=self._creds)]

    @classmethod
    def integration_types(cls) -> list[type]:
        return [ProtonCredentials]
```

The polling job, message processor, signal source, thread map, and REST API all
pick it up automatically — no further wiring required.

### 4. Automated sender classification

Add provider-specific bot patterns to `config.yaml` if needed:

```yaml
messaging:
  automated_senders:
    - "proton-team@proton.me"
    - "@pm\\.me$"          # regex patterns are supported
```

### 5. Tests

```
integrations/ze-proton/tests/
    test_proton_channel.py
```

Test `send()`, `get_thread()`, `poll_new_messages()`, and error wrapping.
No real API calls — mock the transport client.

---

## Checklist

- [ ] `InboundChannel` subclass with `channel_id`, `send`, `get_thread`, `poll_new_messages`
- [ ] `channel_id` returns `"{provider}:{handle}"` (stable after first use)
- [ ] `headers` populated on `InboundMessage` (for automated sender detection)
- [ ] Transport errors wrapped as `ChannelSendError`
- [ ] Channel exposed via `plugin.channels()`
- [ ] Integration type declared in `plugin.integration_types()`
- [ ] `config.yaml` automated sender patterns added (if needed)
- [ ] Tests written — including error wrapping and poll filtering
