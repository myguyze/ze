# ADR: ntfy for push notifications

> **Status:** Accepted
> **Date:** 2024-03-01 (Phase 7 / Phase 40)
> **Scope:** `ze-notifications`, `ze-api` `NativeAppInterface`, proactive jobs

---

## Context and Problem Statement

Ze needs to push notifications to the user when they are not actively in the web app:
proactive briefings, calendar reminders, goal updates, accountability alerts. This
requires a push channel that works on mobile without an always-on WebSocket connection.

---

## Decision Drivers

- Ze is self-hosted — the push channel should be self-hostable too, or at minimum
  not require vendor approval (no Apple Developer Program just to send a push)
- Deep link support: tapping a notification should open Ze at the right screen
- REST API: notifications must be sendable from a Python background job with no SDK
- No per-device registration or push token management complexity
- Single user: no need for audience segmentation or campaign tooling

---

## Considered Options

1. **Firebase Cloud Messaging (FCM)** — Google's cross-platform push infrastructure
2. **APNs direct** — Apple Push Notification service, iOS-native
3. **ntfy** — open-source, self-hostable, REST-based push; public cloud instance available

---

## Decision Outcome

**Chosen option: ntfy (Option 3).**

ntfy exposes a dead-simple REST API (`PUT https://ntfy.sh/<topic> -d "body"`).
The ntfy app is available on iOS and Android. Topics are the auth mechanism — keep
the topic secret, keep the notifications private. Deep links are supported via ntfy's
`actions` field. Self-hosting is a single Docker container.

### Positive Consequences

- Sending a notification is a single HTTP PUT — no SDK, no token registration
- Works on iOS and Android without Apple Developer Program membership required for sending
- Self-hostable: if ntfy.sh disappears, spin up `ntfy serve` and update `NTFY_BASE_URL`
- `ze-notifications` is a thin wrapper; swapping the backend is one implementation change

### Negative Consequences / Trade-offs

- Users must install the ntfy app — not native iOS/Android push
- ntfy.sh public server rate-limits unauthenticated topics; requires a token for high
  volume (a non-issue for a single-user personal assistant)
- Topic-based auth is weaker than device-token auth — anyone who knows the topic can
  send notifications (mitigated by keeping `NTFY_TOPIC` secret)
- No delivery receipts or read status

---

## Pros and Cons of the Options

### Option 1 — Firebase Cloud Messaging

**Pros:** Battle-tested, high delivery reliability, rich analytics.

**Cons:** Requires a Google account and Firebase project; per-device token registration;
Firebase SDK dependency; no self-hosting; vendor lock-in.

### Option 2 — APNs direct

**Pros:** Native iOS push, highest fidelity on Apple devices.

**Cons:** Requires Apple Developer Program ($99/year); certificate management;
no Android support; complex token lifecycle.

### Option 3 — ntfy

**Pros:** Self-hostable, REST-only, no vendor approval, cross-platform.

**Cons:** Users need the ntfy app; weaker auth model than token-based push.

---

## Links

- [Phase 40 — Notifications](../phases/040-notifications/spec.md)
- `core/ze-notifications/ze_notifications/` — `NtfyNotifier` implementation
- `apps/ze-api/ze_api/interface/native.py` — ntfy fallback in `NativeAppInterface`
