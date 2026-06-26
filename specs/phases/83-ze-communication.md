# Phase 83 — ze-communication + ze-messenger

**Status:** Pending
**Depends on:** Phase 82 (ze-web FSD) — no hard dep, can run in parallel
**Packages touched:** `core/ze-communication` (new), `core/ze-plugin`, `core/ze-sdk`, `integrations/ze-google`, `plugins/ze-email` → renamed `plugins/ze-messenger`, `apps/ze-api`

---

## What this is

The channel abstraction (`Channel` ABC, types, `ChannelRegistry`) currently lives in
`ze-plugin`, which is a plugin framework package — not a communications domain. The
`GmailChannel` implementation sits in `ze-email`, mixing a Google API adapter with
plugin/agent concerns. There is no inbound interface — `poll_replies` is outbound-initiated
polling tied to a specific prospecting use case, not a generic inbound model.

This phase:
1. Extracts a dedicated `core/ze-communication` package that owns the full channel
   contract — types, outbound, inbound (polling-based), and the registry.
2. Moves `GmailChannel` to `integrations/ze-google`, where it belongs as a Google API adapter.
3. Renames `plugins/ze-email` → `plugins/ze-messenger`: a generic cross-channel
   communication plugin whose agent routes through whichever channel is registered for
   a contact.
4. Strips channels from `ze-plugin` (the framework no longer owns domain contracts).

Phase 84 builds on this by adding a webhook push path (`supports_push = True`) and the
`POST /webhooks/{channel}` endpoint. This phase establishes the interface seam that
Phase 84 drops into.

---

## Architectural decisions

| Decision | Choice | Rationale |
|---|---|---|
| Package location | `core/ze-communication` | Channel contracts are infrastructure shared across plugins and integrations — not a plugin concern |
| `GmailChannel` location | `integrations/ze-google` | It is a pure Google API adapter; no Ze domain logic — integrations are the right home |
| Integration deps | `ze-google` may depend on `ze-communication` | The "no Ze deps" rule was about domain knowledge; protocol/type deps are fine |
| Inbound model | `InboundChannel` ABC with `poll_new_messages` + `supports_push: bool` | Polling now, push later — flag lets callers adapt without interface churn |
| Plugin rename | `ze-email` → `ze-messenger` | The plugin is channel-agnostic; Gmail is one implementation; the name should reflect that |
| `ze-plugin` channels | Removed; re-export via `ze-sdk` | `ze-plugin` is a framework; domain contracts live in their own packages |
| Contact preferred channel | `ContactChannelStore.get_preferred()` already exists | No DB changes needed; already wired in `ze-personal` |

---

## Package: `core/ze-communication`

### Location

```
core/ze-communication/
  ze_communication/
    __init__.py
    types.py          # ChannelType, ChannelHandle, Message, SentMessage,
                      # Thread, ThreadMessage, InboundMessage
    channel.py        # Channel ABC (outbound), InboundChannel ABC
    registry.py       # ChannelRegistry
  pyproject.toml
  tests/
    test_registry.py
```

### Dependencies

| Dependency | Purpose |
|---|---|
| `ze-agents` | `ChannelNotFoundError`, `ChannelSendError` from `ze_agents.errors` |

No other Ze deps. No DB. No LLM.

### Types

```python
# ze_communication/types.py

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class ChannelType(StrEnum):
    EMAIL    = "email"
    LINKEDIN = "linkedin"
    WHATSAPP = "whatsapp"


@dataclass
class ChannelHandle:
    channel_type: ChannelType
    handle: str
    preferred: bool = False
    verified: bool = False


@dataclass
class Message:
    channel_type: ChannelType
    to: str
    body: str
    subject: str | None = None
    thread_id: str | None = None


@dataclass
class SentMessage:
    message_id: str
    thread_id: str
    channel_type: ChannelType
    sent_at: datetime


@dataclass
class ThreadMessage:
    message_id: str
    sender: str
    body: str
    sent_at: datetime
    is_outbound: bool


@dataclass
class Thread:
    thread_id: str
    channel_type: ChannelType
    messages: list[ThreadMessage] = field(default_factory=list)


@dataclass
class InboundMessage:
    """A new message received on a channel, not tied to a known outbound thread."""
    message_id: str
    channel_type: ChannelType
    sender: str             # raw handle (email address, phone number, etc.)
    subject: str | None     # channel-specific; None for channels that don't have subjects
    body: str
    thread_id: str | None   # set if this is part of an existing thread
    received_at: datetime
```

### Channel ABCs

```python
# ze_communication/channel.py

from abc import ABC, abstractmethod
from datetime import datetime
from ze_communication.types import (
    ChannelType, Message, SentMessage, Thread, ThreadMessage, InboundMessage
)


class Channel(ABC):
    """Outbound channel contract. All channels must implement this."""

    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    async def send(self, message: Message) -> SentMessage: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Thread: ...


class InboundChannel(Channel):
    """Channel that can also receive messages, via polling or push.

    Polling callers check supports_push first. If False, call poll_new_messages
    on a schedule. If True, messages arrive via the webhook path (Phase 84).
    """

    @property
    def supports_push(self) -> bool:
        return False

    @abstractmethod
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...
```

### Registry

```python
# ze_communication/registry.py

from ze_communication.channel import Channel, InboundChannel
from ze_communication.types import ChannelType
from ze_agents.errors import ChannelNotFoundError


class ChannelRegistry:
    def __init__(self, channels: list[Channel]) -> None:
        self._channels: dict[ChannelType, Channel] = {c.channel_type: c for c in channels}

    def get(self, channel_type: ChannelType) -> Channel:
        try:
            return self._channels[channel_type]
        except KeyError:
            raise ChannelNotFoundError(f"No channel registered for {channel_type!r}")

    def get_inbound(self, channel_type: ChannelType) -> InboundChannel | None:
        ch = self._channels.get(channel_type)
        return ch if isinstance(ch, InboundChannel) else None

    def available(self) -> list[ChannelType]:
        return list(self._channels.keys())

    def inbound_channels(self) -> list[InboundChannel]:
        return [c for c in self._channels.values() if isinstance(c, InboundChannel)]
```

---

## `integrations/ze-google`: add `GmailChannel`

Move `ze_email/channel/gmail.py` → `ze_google/gmail_channel.py`.

`ze-google` gains a dependency on `ze-communication`:

```toml
# integrations/ze-google/pyproject.toml
dependencies = ["ze-communication"]
```

`GmailChannel` becomes an `InboundChannel`:

```python
# ze_google/gmail_channel.py

from ze_communication.channel import InboundChannel
from ze_communication.types import (
    ChannelType, Message, SentMessage, Thread, ThreadMessage, InboundMessage
)


class GmailChannel(InboundChannel):
    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.EMAIL

    @property
    def supports_push(self) -> bool:
        return False  # Phase 84 flips this to True and adds register_push()

    async def send(self, message: Message) -> SentMessage: ...         # unchanged
    async def get_thread(self, thread_id: str) -> Thread: ...          # unchanged
    async def poll_new_messages(self, since: datetime) -> list[InboundMessage]: ...  # new
```

`poll_new_messages` queries Gmail with `q="is:inbox newer_than:Xd"` (or by date),
parses headers, and maps to `InboundMessage`. It does **not** filter by known thread IDs —
that is the caller's job.

The existing `poll_replies` (thread-specific polling for prospecting) stays on the class
for backward compatibility but is a thin wrapper around `get_thread`.

---

## `plugins/ze-messenger` (renamed from `ze-email`)

### What changes

| Before | After |
|---|---|
| `plugins/ze-email/` | `plugins/ze-messenger/` |
| `ze_email` module | `ze_messenger` module |
| `EmailPlugin` | `MessengerPlugin` |
| `EmailAgent` hard-coded to Gmail | `MessengerAgent` routes via `ChannelRegistry` |
| `GmailChannel` imported from `ze_email.channel.gmail` | imported from `ze_google.gmail_channel` |

### MessengerPlugin

```python
class MessengerPlugin(ZePlugin):
    def __init__(self, google_credentials: GoogleCredentials | None = None) -> None:
        self._google_credentials = google_credentials

    def channels(self) -> list[Channel]:
        if self._google_credentials is None:
            return []
        return [GmailChannel(credentials=self._google_credentials)]

    def memory_policies(self) -> dict:
        from ze_memory.policies import EmailPolicy
        return {"email": EmailPolicy()}

    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]

    def agent_module_paths(self) -> list[str]:
        if self._google_credentials is None:
            return []
        return [
            "ze_messenger.agents.messenger.tools",
            "ze_messenger.agents.messenger.agent",
        ]
```

### MessengerAgent

The agent keeps Gmail-specific tools (`list_emails`, `get_email`, `draft_email`,
`send_email`, `archive_email`) for now — they are Gmail tools, not generic. The agent
description broadens to reflect multi-channel intent in future:

```python
@agent
class MessengerAgent(BaseAgent):
    name = "messenger"
    display_name = "Messenger"
    description = """
      Messaging and inbox management across communication channels.
      Use for: "do I have any emails from X", "check my inbox", "what's in my email",
      "draft a message to X about Y", "send an email to X", "reply to X's email",
      "forward this email", "summarise my email thread", "archive this email",
      "search my inbox for X". Not for calendar events or reminders.
    """
    ...
```

The `deps` dict passed to `agentic_loop` gains `channel_registry` so tools can resolve
channels by type rather than importing `GmailChannel` directly. This is the seam for
adding non-Gmail channels later.

---

## `core/ze-plugin`: remove channels submodule

`ze_plugin/channels/` is deleted. `ze-plugin` removes its dep on channel types.

Any code that imported from `ze_plugin.channels.*` or `ze_sdk.channels.*` migrates to
`ze_communication.*` (or `ze_sdk.channels.*` which re-exports from there — see below).

---

## `core/ze-sdk`: re-export from `ze-communication`

```python
# ze_sdk/channels.py  (replaces current content)
from ze_communication.types import (
    ChannelType, ChannelHandle, Message, SentMessage,
    Thread, ThreadMessage, InboundMessage,
)
from ze_communication.channel import Channel, InboundChannel
from ze_communication.registry import ChannelRegistry

__all__ = [
    "ChannelType", "ChannelHandle", "Message", "SentMessage",
    "Thread", "ThreadMessage", "InboundMessage",
    "Channel", "InboundChannel", "ChannelRegistry",
]
```

Plugin code continues to `from ze_sdk.channels import ...` — no import changes needed
in plugins beyond removing any direct `ze_plugin.channels` imports.

---

## `apps/ze-api`: wiring

- Replace `EmailPlugin` registration with `MessengerPlugin`.
- `ChannelRegistry` is built from all plugin `.channels()` results — no change to that
  mechanism; just the class name changes.
- Route description update: `email` agent name → `messenger` in routing embeddings
  (a one-time re-embed is needed, or add `messenger` as an alias intent).

---

## Migration

No DB changes. `contact_channels` table and `ContactChannelStore` are unchanged — they
already use `ChannelType` which comes from `ze_sdk.channels`.

---

## Implementation sequence

### 83a — Core package + types

1. Create `core/ze-communication/` with `types.py`, `channel.py`, `registry.py`, `pyproject.toml`
2. Add `ze-communication` dep to `ze-sdk`; update `ze_sdk/channels.py` to re-export
3. Remove `ze_plugin/channels/` submodule; remove dep from `ze-plugin/pyproject.toml`
4. Fix any imports in `ze-core`, `ze-personal` that used `ze_plugin.channels.*`

### 83b — GmailChannel migration

1. Add `ze-communication` dep to `ze-google/pyproject.toml`
2. Move `ze_email/channel/gmail.py` → `ze_google/gmail_channel.py`
3. Implement `InboundChannel` on `GmailChannel` (add `poll_new_messages`)
4. Update imports in `ze-email` agent and plugin (temporarily, before rename)

### 83c — ze-email → ze-messenger rename

1. Rename directory `plugins/ze-email` → `plugins/ze-messenger`
2. Rename module `ze_email` → `ze_messenger`
3. Rename `EmailPlugin` → `MessengerPlugin`, `EmailAgent` → `MessengerAgent`
4. Update `ze-api/pyproject.toml` dep and `container.py` plugin registration
5. Update routing agent name (`email` → `messenger`) + re-embed descriptions
6. Update all cross-package imports

### 83d — Tests + cleanup

1. Port `ze-email` tests to `ze-messenger`
2. Add `ze-communication` unit tests (`test_registry.py`, `test_types.py`)
3. Update `specs/README.md` phase table
4. Update `CLAUDE.md` package layout, dep graph, plugin table

---

## Success criteria

- `make test-messenger` passes (renamed from `make test-email`)
- `make test-communication` passes
- `make lint` clean across all packages
- No imports of `ze_plugin.channels.*` remain in the codebase
- `GmailChannel` is importable from `ze_google.gmail_channel`
- `MessengerPlugin` replaces `EmailPlugin` in `ze_api/container.py`
- Email agent still routes correctly end-to-end (email send/read tools work)
