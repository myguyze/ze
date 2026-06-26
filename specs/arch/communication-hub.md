# Architecture: Communication Hub

**Status:** Active
**Related phases:** 83 (channel contract), 85 (messaging hub), 86 (webhooks)

---

## What this is

Ze functions as a communication hub: it connects to the user's messaging channels, understands
what flows through them, and integrates that understanding into memory and the correlation engine.
This document captures the invariants that all channel implementations and phases must respect.
Phase specs describe *how* to implement; this document describes *what must always be true*.

---

## Channel identity

Every channel instance has a stable string `channel_id` of the form `"{provider}:{handle}"`:

```
gmail:joao@gmail.com
gmail:joao@work.com
proton:joao@protonmail.com
whatsapp:+351912345678
```

**Invariants:**
- `channel_id` is unique across all registered instances. Two Gmail accounts must have
  different `channel_id` values. The registry enforces this via a `dict[channel_id, InboundChannel]`
  secondary index.
- `channel_id` is stable once resolved. A channel that resolves its handle lazily (e.g.,
  `GmailChannel` resolving the authenticated email address on first use) must not change
  its `channel_id` after writing it to any store.
- The fallback `channel_id` (before resolution) is `channel_type.value`. Code that writes
  a `channel_id` to the database must only do so after resolution, not with the fallback.

The `ChannelType` enum identifies the *protocol* (`email`, `whatsapp`). `channel_id`
identifies the *instance*. Routing, watermarks, and thread ownership all key off `channel_id`,
never `ChannelType` alone.

---

## Thread ownership

A thread belongs to exactly one of Ze's channel instances — the one that received or sent
the first message in that thread. This ownership is recorded in `thread_channel_map` and
is immutable: once a thread is associated with `gmail:joao@gmail.com`, all subsequent
replies from Ze use that same account.

**Why:** Reply continuity is a social contract. The recipient sees the email coming from
the account they originally addressed. Breaking this by using a different account on reply
would be confusing and potentially damaging (e.g., sending a work reply from a personal account).

**Implementation:** `ThreadChannelMap` is the single source of truth. It is populated by:
- `InboundMessageProcessor.process()` — for every polled/pushed message that has a `thread_id`
- `send_email` tool — after every successful send

The routing decision in `send_email` is:
1. Thread known → use its mapped channel
2. No thread or not in map → use `is_default_outbound` channel
3. No default → use any available channel of the right type

No other routing heuristic (contact handle matching, etc.) is implemented until there is
evidence the above is insufficient.

---

## Memory contribution policy

**Problem:** Email volume is high and content is heterogeneous. Applying uniform memory
writes to all inbound messages produces clutter: automated mail generates facts that decay
immediately, signals that dilute real patterns, and episodes that contaminate session
consolidation.

**Solution:** Sender classification gates which memory paths activate.

### Sender classification

Classify the sender of each inbound message before any memory write:

| Class | Criteria |
|---|---|
| **Known contact** | Sender handle is in `contact_channels` |
| **Replied-to** | Thread is in `thread_channel_map` on the outbound side (Ze sent a message in this thread) |
| **Unknown human** | Not in contacts, not replied-to, sender address does not match automated patterns |
| **Automated** | Sender matches automated patterns (see below) |

Automated sender patterns (header-based, no LLM):
- Address prefixes: `noreply@`, `no-reply@`, `notifications@`, `postmaster@`, `mailer-daemon@`,
  `donotreply@`, `bounce@`, `support@` (last one configurable — some support@ are human)
- `List-Unsubscribe` header present
- `Precedence: bulk` or `Precedence: list` header
- Configurable blocklist in `config.yaml` under `messaging.automated_senders`

### Memory write matrix

| Sender class | Episode | Async fact pass | Signal |
|---|---|---|---|
| Known contact | ✅ | ✅ | ✅ |
| Replied-to | ✅ | ✅ | ✅ |
| Unknown human | ✅ (no LLM) | ❌ | ❌ |
| Automated | ❌ | ❌ | ❌ |

**Episode for unknown human:** Written immediately, no LLM pass. Keeps the message
searchable ("what did that investor email last month?") without polluting the fact graph.
Episode metadata includes `sender_class: "unknown_human"` so consolidation can treat
these differently from conversation episodes.

**No contact proposals in this pipeline:** Proposing contacts from unknown senders is a
separate concern with its own confidence/confirmation logic. `InboundMessageProcessor`
never creates contact proposals — it only reads from contacts, it does not write.

### Session consolidation guard

Inbound messages have no conversation session. To prevent them from being grouped with
conversation episodes by the session consolidation job, episodes written by
`InboundMessageProcessor` use a fixed agent value of `"messenger"`. The session
consolidation job must exclude episodes where `agent = "messenger"` from session grouping.
A separate consolidation pass for messaging episodes (e.g., daily digest per sender) is
a future concern.

---

## Signal policy

Signals from messaging feed the correlation engine alongside calendar and news signals.
The signal filter follows the memory write matrix: only known-contact and replied-to
messages emit signals.

**Signal shape:**
```python
Signal(
    source="messaging",
    external_ref=msg.message_id,   # dedup key — admission gate skips if seen
    title=msg.subject or f"Message from {msg.sender}",
    summary=msg.body[:500],
    occurred_at=msg.received_at,
    entities=[EntityRef(name=msg.sender, entity_type="person")],
    magnitude=0.0,                 # reserved; see magnitude note below
    payload={"channel_type": ..., "thread_id": ..., "sender": ...},
)
```

**Magnitude:** All messaging signals start at `0.0`. Future versions may raise magnitude
for messages that triggered a Ze action (Ze replied, Ze created a reminder, Ze extracted
a task) — this is a signal that the message was meaningfully acted on. Do not set
magnitude based on message length or sender reputation without a concrete signal design.

**Dedup:** `external_ref = message_id`. The admission gate in `ze-memory` deduplicates
by `(source, external_ref)` — restarting the polling job or replaying webhooks never
double-counts a message.

---

## Extensibility contract

Adding a new channel (ProtonMail, WhatsApp, Slack) requires:

1. Implement `InboundChannel` in a new integration package (`integrations/ze-proton/`,
   `integrations/ze-whatsapp/`, etc.):
   - `channel_type` — one of the existing `ChannelType` values, or add a new one
   - `channel_id` — override to return `"{provider}:{handle}"`
   - `send()`, `get_thread()` — outbound operations
   - `poll_new_messages(since)` — returns `list[InboundMessage]`; `subject` is `None`
     for channels that don't have a subject concept
   - `supports_push` — return `True` if Phase 86 webhook support is implemented

2. Wire the channel instance into a plugin's `channels()` method. The polling job,
   message processor, signal source, thread map, and REST API all pick it up automatically.

3. Add automated sender classification rules to `messaging.automated_senders` in
   `config.yaml` if the new channel has platform-specific bot patterns.

**No other packages need to change.** `MessengerAgent`, `MessengerPlugin`, `InboundPollingJob`,
`InboundMessageProcessor`, and `MessagingSignalSource` are all channel-agnostic by design.

The one exception: `list_emails`, `get_email`, and `archive_email` tools are Gmail-specific
and will not work for ProtonMail or WhatsApp. These tools must be abstracted or replaced when
a second email provider is added. Until then, `MessengerAgent._default_channel()` injects
Gmail credentials for those tools; routing for `send_email` is already channel-agnostic.

---

## What this is not

**Not a message store.** Ze does not maintain a replica of the user's inbox. Episodes capture
the semantic content of significant messages; the canonical store is the provider (Gmail, etc.).
`get_email` and `list_emails` always fetch from the provider, not from Ze's memory.

**Not a notification router.** Ze notifies the user when a known contact sends a message.
It does not route all notifications from all channels. Unknown senders, automated senders,
and bulk mail do not generate push notifications.

**Not an auto-reply system.** Ze reads and sends on the user's behalf when instructed.
It does not autonomously reply to inbound messages without explicit user action or a
pre-configured workflow.

**Not a full-text search index.** Episode search retrieves messages by semantic similarity.
For keyword search within Gmail, use the Gmail search tools which delegate to the Gmail API.

---

## Open questions

- [ ] **Replied-to classification:** `thread_channel_map` currently only records the channel
  (outbound routing). To classify "replied-to" we need to know whether Ze sent an outbound
  message in this thread. Should `thread_channel_map` carry a `has_outbound: bool` flag,
  or is a separate `outbound_threads` set simpler?
- [ ] **Messaging episode consolidation:** What does a good consolidation of 20 known-contact
  email episodes look like? Per-sender daily digest? Per-thread summary? Defer until volume
  data shows the shape of the problem.
- [ ] **Automated sender blocklist seeding:** Ship a sensible default list (`noreply@` patterns)
  or leave it empty and let the user configure? Recommendation: ship defaults, document how to
  extend.
