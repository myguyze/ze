# ze-communication — Channel Contract

> **Package:** `core/ze-communication` — `ze_communication/`
> **Status:** Done
> **Implemented in:** [Phase 83](../phases/83-ze-communication.md)
> **Architecture:** [arch/communication-hub.md](../arch/communication-hub.md)

---

## Purpose

Defines the abstract channel contract: outbound `Channel` ABC, inbound
`InboundChannel` ABC, `ChannelRegistry`, and the shared channel types. No transport
implementations live here — Gmail (`GmailChannel`) lives in `ze-google`;
future channels (Slack, iMessage) follow the same pattern.

---

## Responsibilities

- `Channel` ABC — outbound: `send(handle, message)`, `reply(thread, message)`
- `InboundChannel` ABC — polling: `poll_since(watermark) -> list[InboundMessage]`
- `ChannelRegistry` — maps `ChannelType` to `Channel` instances; injected into
  `MessengerAgent` and any tool that sends messages
- Shared types — `ChannelType`, `ChannelHandle`, `Message`, `SentMessage`, `Thread`,
  `InboundMessage`
- Webhook plumbing types — `WebhookRegistration` (for push-based inbound channels)

---

## Out of Scope

- Transport implementations — `ze-google` (Gmail), future channel packages
- Message processing and routing — `ze-messenger`
- Contact channel store — `ze-personal`

---

## Module Location

```
core/ze-communication/ze_communication/
  channel.py     ← Channel ABC, InboundChannel ABC
  registry.py    ← ChannelRegistry
  types.py       ← ChannelType, ChannelHandle, Message, SentMessage, Thread, InboundMessage
  webhook.py     ← WebhookRegistration type
```

---

## Interface Contract

```python
class Channel(ABC):
    channel_type: ChannelType

    @abstractmethod
    async def send(self, handle: ChannelHandle, message: Message) -> SentMessage: ...

    @abstractmethod
    async def reply(self, thread: Thread, message: Message) -> SentMessage: ...

class InboundChannel(Channel, ABC):
    @abstractmethod
    async def poll_since(self, watermark: datetime) -> list[InboundMessage]: ...
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze-agents` | Error hierarchy |

---

## Links

- [Phase 27 — Channels](../phases/27-channels.md)
- [Phase 83 — ze-communication + ze-messenger](../phases/83-ze-communication.md)
- [Phase 85 — Messaging Hub](../phases/85-messaging-hub.md)
