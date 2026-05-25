# Ze — Adding a New Channel

This guide explains how to implement a new outbound communication channel
(e.g. LinkedIn DM, WhatsApp). Read it alongside the existing `EmailChannel`
(`ze/channels/email.py`) as a working example.

---

## Before you start

1. Write a spec in `specs/` first. No implementation begins without one.
2. Confirm the transport API supports the three required operations:
   **send**, **get_thread**, and **poll_replies**.

---

## 1. Add the `ChannelType` enum value

In `ze/channels/types.py`, add a new value to `ChannelType`:

```python
class ChannelType(StrEnum):
    EMAIL    = "email"
    LINKEDIN = "linkedin"   # ← add your value here
    WHATSAPP = "whatsapp"
```

The string value is stored in the database — choose it carefully and never
change it after the first migration.

---

## 2. Implement the `Channel` subclass

Create `ze/channels/<name>.py` and implement the `Channel` ABC:

```python
from ze.channels.base import Channel
from ze.channels.types import ChannelType, Message, SentMessage, Thread, ThreadMessage

class LinkedInChannel(Channel):
    def __init__(self, credentials: LinkedInCredentials) -> None:
        self._creds = credentials

    @property
    def channel_type(self) -> ChannelType:
        return ChannelType.LINKEDIN

    async def send(self, message: Message) -> SentMessage:
        # Call the transport API.
        # Raise ChannelSendError (from ze/errors.py) on failure — never let
        # raw transport exceptions escape the channel boundary.
        ...

    async def get_thread(self, thread_id: str) -> Thread:
        # Return all messages in the thread, sorted by sent_at ascending.
        ...

    async def poll_replies(
        self,
        thread_ids: list[str],
        since: datetime,
    ) -> list[ThreadMessage]:
        # Return only inbound (is_outbound=False) messages sent after `since`.
        ...
```

### Contract requirements

| Method | Requirements |
|---|---|
| `send` | Must return a `SentMessage` with a non-empty `message_id` and `thread_id`. If the transport doesn't separate these, use the message ID as the thread ID. |
| `get_thread` | Messages must be sorted by `sent_at` ascending. `is_outbound=True` for messages Ze sent; `False` for replies. |
| `poll_replies` | Must not return outbound messages. Filter client-side if the API doesn't support it. |

### Error handling

Wrap transport exceptions in `ze/errors.py` types before they surface:

```python
from ze.errors import ChannelSendError, ChannelNotFoundError

try:
    result = await transport.send(...)
except SomeTransportError as exc:
    raise ChannelSendError(str(exc)) from exc
```

---

## 3. Wire in `ze/container.py`

Instantiate the channel and pass it to `ChannelRegistry`:

```python
from ze.channels.linkedin import LinkedInChannel

linkedin_channel = LinkedInChannel(credentials=linkedin_creds)

channel_registry = ChannelRegistry(channels=[
    email_channel,
    linkedin_channel,   # ← add here
])
```

The registry is keyed by `channel_type` — duplicate types raise at construction.

---

## 4. Write a migration if needed

If the new channel requires credentials or config stored in the database, add
a migration in `migrations/versions/` following the existing raw-SQL pattern.

The `contact_channels` table already supports any `ChannelType` value — no
schema change is needed just to store handles for the new channel.

---

## 5. Write tests

```
tests/channels/
    test_<name>_channel.py
```

Conventions:

- No real API calls. Mock the transport client with `AsyncMock`.
- Test `send()`, `get_thread()`, and `poll_replies()` independently.
- Test that transport errors are wrapped as `ChannelSendError`, not re-raised raw.
- Test `poll_replies()` filters out outbound messages and messages before `since`.

```python
async def test_send_wraps_transport_error(mock_creds):
    channel = LinkedInChannel(mock_creds)
    mock_creds.client.send.side_effect = SomeTransportError("network failure")
    with pytest.raises(ChannelSendError, match="network failure"):
        await channel.send(Message(channel_type=ChannelType.LINKEDIN, to="...", body="..."))
```

---

## 6. Expose to agents (if needed)

If agents need to send via the new channel, no agent code changes are
required — they look up channels by type from `ChannelRegistry`:

```python
channel = channel_registry.get(ChannelType.LINKEDIN)
sent = await channel.send(message)
```

Agents that already use `get_contact_channels` will automatically surface
LinkedIn handles once contacts have them stored.

---

## Checklist

- [ ] Spec written and reviewed
- [ ] `ChannelType` enum value added to `ze/channels/types.py`
- [ ] `ze/channels/<name>.py` — `Channel` subclass with all three methods
- [ ] Transport errors wrapped as `ChannelSendError` (never raw)
- [ ] Channel instantiated and added to `ChannelRegistry` in `ze/container.py`
- [ ] Migration written (if credentials/config need DB storage)
- [ ] Tests written — including error wrapping and reply filtering
