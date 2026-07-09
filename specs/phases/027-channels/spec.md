# Spec 27 — Communication Channel Abstraction

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze/channels/` module — `Channel` ABC, `Message`, `Thread`, `ChannelType` types | ✅ Done |
| `ze/channels/email.py` — `EmailChannel` (send + thread tracking + reply detection) | ✅ Done |
| `ze/channels/registry.py` — channel registry | ✅ Done |
| Migration 015 — `contact_channels` table | ✅ Done |
| `ContactChannelStore` — CRUD for per-contact channel handles | ✅ Done |
| Email agent refactor — delegates transport to `EmailChannel` | ✅ Done |
| `get_contact_channels` tool — expose channel handles to agents | ✅ Done |
| `set_contact_channel` tool — add/update a channel handle for a contact | ✅ Done |
| Container wiring | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze needs to reach people through multiple channels — email today, LinkedIn and
WhatsApp later. This spec establishes a channel abstraction that:

1. Defines a common interface any channel must implement (send, reply detection,
   thread tracking).
2. Refactors the existing email transport into the first `Channel` implementation.
3. Extends the contacts system so Ze knows which channels are available for a
   given person and which to prefer.

Future channels (LinkedIn DM, WhatsApp) are out of scope here but must require
only a new `Channel` subclass and a new `ChannelType` enum value — no changes to
agents or the contacts schema.

---

## Out of Scope

- LinkedIn or WhatsApp channel implementations (future phases).
- Inbound message polling / reply surfacing to Telegram (future phase — builds on
  this foundation).
- Channel-level rate limiting beyond what Gmail API enforces.
- Multi-account support (Ze has one Gmail identity).

---

## Repository Layout

```
ze/
├── ze/
│   ├── channels/
│   │   ├── __init__.py        # exports Channel, ChannelType, Message, Thread
│   │   ├── base.py            # Channel ABC
│   │   ├── email.py           # EmailChannel
│   │   ├── registry.py        # ChannelRegistry
│   │   └── types.py           # ChannelType, Message, Thread, ChannelHandle
│   ├── contacts/
│   │   ├── channel_store.py   # ContactChannelStore
│   │   └── ...                # existing contact modules unchanged
│   └── agents/
│       └── email/
│           └── agent.py       # refactored to use EmailChannel
└── migrations/versions/
    └── 015_contact_channels.py
```

---

## Types (`ze/channels/types.py`)

```python
@dataclass
class ChannelHandle:
    channel_type: ChannelType
    handle: str          # email address, LinkedIn URL, WhatsApp number, etc.
    preferred: bool      # True = use this channel first for this contact
    verified: bool       # True = Ze has successfully used this handle

@dataclass
class Message:
    channel_type: ChannelType
    to: str              # recipient handle
    subject: str | None  # email only
    body: str
    thread_id: str | None = None   # attach to existing thread if set

@dataclass
class SentMessage:
    message_id: str
    thread_id: str
    channel_type: ChannelType
    sent_at: datetime

@dataclass
class Thread:
    thread_id: str
    channel_type: ChannelType
    messages: list[ThreadMessage]   # ordered oldest→newest

@dataclass
class ThreadMessage:
    message_id: str
    sender: str
    body: str
    sent_at: datetime
    is_outbound: bool   # True = Ze sent this
```

`ChannelType` is a `StrEnum`:

```python
class ChannelType(StrEnum):
    EMAIL    = "email"
    LINKEDIN = "linkedin"
    WHATSAPP = "whatsapp"
```

---

## `Channel` ABC (`ze/channels/base.py`)

```python
class Channel(ABC):
    @property
    @abstractmethod
    def channel_type(self) -> ChannelType: ...

    @abstractmethod
    async def send(self, message: Message) -> SentMessage: ...

    @abstractmethod
    async def get_thread(self, thread_id: str) -> Thread: ...

    # Returns messages received since `since`. Empty list if unsupported.
    @abstractmethod
    async def poll_replies(
        self,
        thread_ids: list[str],
        since: datetime,
    ) -> list[ThreadMessage]: ...
```

Every channel must implement all three methods. Channels that cannot poll replies
(e.g. a future SMS channel) return `[]` from `poll_replies`.

---

## `EmailChannel` (`ze/channels/email.py`)

Wraps the Gmail API calls currently spread across `ze/agents/email/tools.py`.
Takes `GoogleCredentials` as a constructor argument — no change to auth flow.

Key behaviours:
- `send()` — calls `gmail.users.messages.send`. If `message.thread_id` is set,
  attaches `threadId` to the Gmail request so it stays in the same thread.
- `get_thread()` — fetches all messages in the thread, parses sender/body/date,
  marks each as `is_outbound` by checking against the authenticated user's address.
- `poll_replies()` — for each `thread_id`, fetches the thread and returns any
  `ThreadMessage` where `sent_at > since` and `is_outbound=False`.

The Gmail API client is constructed from `GoogleCredentials` the same way the
existing email tools do it — no new auth primitives.

---

## `ChannelRegistry` (`ze/channels/registry.py`)

```python
class ChannelRegistry:
    def __init__(self, channels: list[Channel]) -> None: ...
    def get(self, channel_type: ChannelType) -> Channel: ...   # raises ChannelNotFoundError
    def available(self) -> list[ChannelType]: ...
```

Constructed in `container.py` with `[EmailChannel(...)]`. Adding a new channel
later is one line in the container.

---

## Contact Channels

### Migration 015 — `contact_channels` table

```sql
CREATE TABLE contact_channels (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_id   UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    channel_type TEXT        NOT NULL,   -- ChannelType value
    handle       TEXT        NOT NULL,
    preferred    BOOLEAN     NOT NULL DEFAULT FALSE,
    verified     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(contact_id, channel_type, handle)
);
CREATE INDEX contact_channels_contact_id_idx ON contact_channels(contact_id);
CREATE INDEX contact_channels_type_idx       ON contact_channels(channel_type);
```

The existing `contact_info` JSONB on the `contacts` table is **not** migrated
automatically — it remains as unstructured context. New channel handles go into
`contact_channels`. The email agent's contact extractor should write to
`contact_channels` going forward.

### `ContactChannelStore` (`ze/contacts/channel_store.py`)

```python
class ContactChannelStore:
    async def get_handles(self, contact_id: UUID) -> list[ChannelHandle]: ...
    async def get_preferred(self, contact_id: UUID) -> ChannelHandle | None: ...
    async def upsert(self, contact_id: UUID, handle: ChannelHandle) -> None: ...
    async def set_preferred(self, contact_id: UUID, channel_type: ChannelType) -> None: ...
    async def delete(self, contact_id: UUID, channel_type: ChannelType, handle: str) -> None: ...
```

`upsert` uses `ON CONFLICT (contact_id, channel_type, handle) DO UPDATE`.

---

## Agent Tools

Two new tools registered in `ze/tools/contacts.py` (alongside existing contact
tools):

### `get_contact_channels`

Input: `contact_id: str`
Output: list of `{channel_type, handle, preferred, verified}` dicts.

Used by the email agent and (future) prospecting agent to determine how to reach
a contact before sending.

### `set_contact_channel`

Input: `contact_id: str, channel_type: str, handle: str, preferred: bool = False`
Output: confirmation string.

Lets an agent record a newly discovered handle (e.g. prospecting agent finds a
LinkedIn URL, email agent extracts an address from a signature).

---

## Email Agent Refactor

`ze/agents/email/tools.py` currently calls Gmail API directly. After this phase:

- `send_email` tool calls `EmailChannel.send()`.
- `get_email` / `list_emails` tools remain as Gmail-specific reads — they are not
  part of the `Channel` interface (read access is channel-specific and not needed
  by the abstraction).
- `draft_email` remains Gmail-specific (drafts are not a cross-channel concept).
- Contact extraction (`extract_email_contacts`) writes email handles to
  `contact_channels` via `ContactChannelStore.upsert()` in addition to whatever
  it currently writes to `contact_info`.

The agent's public interface (tool names, `AgentContext`, routing) is unchanged.

---

## Container Wiring

```python
email_channel = EmailChannel(google_credentials=google_credentials)
channel_registry = ChannelRegistry(channels=[email_channel])
contact_channel_store = ContactChannelStore(pool=pool)

register_instance(ChannelRegistry, channel_registry)
register_instance(ContactChannelStore, contact_channel_store)
```

`EmailChannel` is injected into the email agent's tools via the existing
`deps={"credentials": ...}` pattern — or directly via the `ChannelRegistry`.

---

## Error Handling

New errors in `ze/errors.py`:

```python
class ChannelError(ZeError): ...
class ChannelNotFoundError(ChannelError): ...   # registry miss
class ChannelSendError(ChannelError): ...       # transport failure
```

---

## Testing

- `tests/channels/test_email_channel.py` — mock Gmail API responses; test `send`,
  `get_thread`, `poll_replies` (including the `is_outbound` detection logic).
- `tests/contacts/test_channel_store.py` — mock asyncpg pool; test upsert,
  preferred logic, conflict resolution.
- `tests/tools/test_contact_channel_tools.py` — mock `ContactChannelStore`; test
  `get_contact_channels` and `set_contact_channel`.
- Email agent tests: update to mock `EmailChannel` instead of raw Gmail calls.
- No slow tests in this phase.

---

## What This Enables

After this phase:

- Ze knows for each contact: "I can reach them via email at X, and LinkedIn at Y
  (once LinkedIn channel is implemented)."
- The prospecting agent can call `get_contact_channels` before deciding how to
  send outreach, and `set_contact_channel` when it discovers a new handle.
- Adding LinkedIn or WhatsApp is: one new `Channel` subclass + one new
  `ChannelType` value + one line in the container. No agent changes needed.
- Reply detection (`poll_replies`) is wired at the transport layer, ready for the
  follow-up phase to build on.
