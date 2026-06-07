# Notifications — Spec

> **Package:** `ze-notifications` (new package, no ze deps)
> **Phase:** 40
> **Status:** Done
> **Depends on:** Phase 40 ([40-native-ui-foundation.md](40-native-ui-foundation.md))

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `Notification` type | ✅ Done |
| `Notifier` Protocol | ✅ Done |
| `NtfyNotifier` | ✅ Done |
| Deep link encoding | ✅ Done |
| Startup token validation | ✅ Done |
| `ze/` wiring update (replace inline ntfy from Phase 40) | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Phase 40 specced an inline `NtfyClient` inside `ze/notifications/ntfy.py`. That works but
bakes the implementation into the application layer, making it impossible for domain
packages (`ze-personal`, `ze-finance`, `ze-legal`, `ze-news`) to push notifications without
depending on `ze`.

This phase extracts the notification concern into a standalone `ze-notifications` package
with a `Notifier` Protocol and a single `NtfyNotifier` implementation. Any package can
declare a `Notifier` dependency and push notifications — the wiring of which implementation
is used stays in `ze/container.py`.

The `Notification` type gains a `data` field for deep linking: when the user taps a
notification on their phone, the Flutter app navigates to the relevant screen.

---

## Responsibilities

- Define `Notification` as the canonical type for all Ze push notifications.
- Define `Notifier` as a Protocol so any package can depend on the interface without
  importing the implementation.
- Implement `NtfyNotifier` — the ntfy HTTP backend — as the one concrete implementation.
- Encode `Notification.data` as a deep link URL passed to ntfy's `Click` header, so the
  Flutter app can navigate on tap.
- Enforce at startup that ntfy.sh topics have a token configured.
- Replace the inline `NtfyClient` in Phase 40's `ze/notifications/ntfy.py` with a
  dependency on `ze-notifications`.

---

## Out of Scope

- In-app notification display or a notification centre — that is Flutter (Phase 43).
- Multiple simultaneous notifier backends (fan-out to ntfy + APNs, etc.) — future scope.
- Per-notification routing to different topics — one topic per Ze instance for now.
- Rate limiting or deduplication of notifications — future scope.
- Notification history or read/unread tracking — the `messages` table (Phase 40) covers
  this; there is no separate notification store.

---

## Package Layout

```
packages/ze-notifications/
  pyproject.toml          ← no ze deps; aiohttp only
  ze_notifications/
    __init__.py
    types.py              ← Notification, NotificationPriority
    notifier.py           ← Notifier Protocol
    ntfy.py               ← NtfyConfig, NtfyNotifier
```

### Updated package dependency graph

```
ze-browser       (no ze deps)
ze-core          (no ze deps)
ze-components    (no ze deps)
ze-notifications (no ze deps)
ze-personal      → ze-core
ze               → ze-core, ze-personal, ze-browser, ze-components, ze-notifications
ze-finance       → ze-core, ze-personal
ze-legal         → ze-core, ze-personal
ze-news          → ze-core, ze-personal
```

Domain packages that need to push notifications add `ze-notifications` as a dependency
and accept a `Notifier` in their constructors. The concrete implementation is wired in
`ze/container.py`, as with all other infrastructure.

---

## Data Structures

```python
# ze_notifications/types.py

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal

NotificationPriority = Literal[1, 2, 3, 4, 5]
# 1 = min  (silent background sync)
# 2 = low
# 3 = default
# 4 = high
# 5 = urgent (used for stuck goals, critical alerts)


@dataclass
class Notification:
    title: str
    body: str
    priority: NotificationPriority = 3
    tags: list[str] | None = None
    # Deep link payload. On tap, the Flutter app receives:
    #   ze://navigate?<key>=<value>&...
    # Keys are app-defined; see Deep Linking section below.
    data: dict[str, str] | None = None
```

---

## Notifier Protocol

```python
# ze_notifications/notifier.py

from typing import Protocol
from ze_notifications.types import Notification


class Notifier(Protocol):
    async def push(self, notification: Notification) -> None:
        """
        Push a notification. Implementations must:
        - Never raise on delivery failure (log and return).
        - Be async.
        """
        ...
```

---

## NtfyNotifier

```python
# ze_notifications/ntfy.py

import json
import urllib.parse
from dataclasses import dataclass
import aiohttp
from ze_notifications.types import Notification
from ze_notifications.notifier import Notifier


@dataclass
class NtfyConfig:
    base_url: str       # "https://ntfy.sh" or self-hosted URL (no trailing slash)
    topic: str          # e.g. "ze-joao-abc123" — keep non-guessable for ntfy.sh
    token: str | None   # Bearer token; required when base_url contains "ntfy.sh"


class NtfyNotifier:
    def __init__(self, config: NtfyConfig, session: aiohttp.ClientSession) -> None:
        self._config = config
        self._session = session
        self._url = f"{config.base_url}/{config.topic}"

    async def push(self, notification: Notification) -> None:
        headers = self._build_headers(notification)
        try:
            async with self._session.post(
                self._url,
                data=notification.body.encode(),
                headers=headers,
            ) as resp:
                if resp.status >= 400:
                    log.warning(
                        "ntfy_push_failed",
                        status=resp.status,
                        topic=self._config.topic,
                    )
        except Exception as exc:
            log.warning("ntfy_push_error", error=str(exc))

    def _build_headers(self, n: Notification) -> dict[str, str]:
        headers: dict[str, str] = {
            "X-Title":    n.title,
            "X-Priority": str(n.priority),
        }
        if self._config.token:
            headers["Authorization"] = f"Bearer {self._config.token}"
        if n.tags:
            headers["X-Tags"] = ",".join(n.tags)
        if n.data:
            headers["X-Click"] = _encode_deep_link(n.data)
        return headers


def _encode_deep_link(data: dict[str, str]) -> str:
    """Encode a data dict as a ze:// deep link URL."""
    return "ze://navigate?" + urllib.parse.urlencode(data)
```

### Startup validation

`NtfyNotifier.__init__` raises `ZeConfigError` if `base_url` contains `"ntfy.sh"` and
`token` is `None`. ntfy.sh topics without a token are publicly readable.

```python
def __init__(self, config: NtfyConfig, session: aiohttp.ClientSession) -> None:
    if "ntfy.sh" in config.base_url and not config.token:
        raise ZeConfigError(
            "NTFY_TOKEN is required for ntfy.sh topics. "
            "Set token in config or switch to a self-hosted ntfy instance."
        )
    ...
```

---

## Deep Linking

The `data` dict is encoded as query parameters on a `ze://navigate` URL. The Flutter app
registers the `ze://` URL scheme. ntfy passes the URL to the OS on notification tap; the
OS hands it to the Flutter app.

### Defined deep link keys

| Key | Value | Navigates to |
|-----|-------|-------------|
| `screen` | `"chat"` | Main chat screen |
| `screen` | `"goal"` | Goal list |
| `goal_id` | `"<uuid>"` | Specific goal (used with `screen=goal`) |
| `screen` | `"workflow"` | Workflow list |
| `screen` | `"costs"` | Cost summary screen |

Unrecognised keys are silently ignored by the Flutter app — the app opens to the default
screen. New keys can be added as new screens are built without changing the notification
contract.

### Examples

```python
# Morning briefing — open to chat
Notification(
    title="Good morning",
    body="Your briefing is ready.",
    priority=3,
    data={"screen": "chat"},
)

# Stuck goal alert — deep link to the goal
Notification(
    title="Ze — Goal stalled",
    body="'Launch website' has had no activity for 5 days.",
    priority=4,
    tags=["warning"],
    data={"screen": "goal", "goal_id": "abc-123"},
)

# Plain message response — no navigation needed
Notification(
    title="Ze",
    body="Here's your contact list.",
    priority=3,
)
```

---

## Configuration

```yaml
# config/config.yaml
notifications:
  ntfy:
    base_url: "https://ntfy.sh"
    topic: "ze-<random-suffix>"   # non-guessable; generate once at setup
```

```
# .env
NTFY_TOKEN=your-ntfy-token   # required for ntfy.sh; optional for self-hosted
```

---

## ze/ Wiring Update

Phase 40 specced `NtfyClient` inside `ze/notifications/ntfy.py`. That file is removed.
`NativeAppInterface` is updated to accept a `Notifier` (the Protocol) instead of a
concrete `NtfyClient`:

```python
# ze/interface/native.py

class NativeAppInterface(AppInterface):
    def __init__(
        self,
        message_store: MessageStore,
        connection_manager: ConnectionManager,
        notifier: Notifier,            # was: NtfyClient
    ) -> None: ...
```

`ZeContainer` constructs `NtfyNotifier` and registers it as the `Notifier` implementation:

```python
# ze/container.py

from ze_notifications.ntfy import NtfyConfig, NtfyNotifier

ntfy_config = NtfyConfig(
    base_url=settings.ntfy_base_url,
    topic=settings.ntfy_topic,
    token=settings.ntfy_token,
)
notifier = NtfyNotifier(config=ntfy_config, session=http_session)
register_instance(Notifier, notifier)
```

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `aiohttp` | Async HTTP client for ntfy POST |
| `ze_core.errors.ZeConfigError` | Startup validation error — only used in `ze/` wiring, not in `ze-notifications` itself |

Wait — `ze-notifications` has no ze deps. `ZeConfigError` is from `ze_core`. To keep
`ze-notifications` dep-free, the startup validation raises a plain `ValueError` instead.
The `ze/container.py` catches it and re-raises as `ZeConfigError` if desired, or the
plain `ValueError` is acceptable at startup.

---

## Implementation Notes

- **`Notifier` is a Protocol, not an ABC.** Any class with a matching `push()` signature
  satisfies it without explicit inheritance. This makes testing trivial — an `AsyncMock`
  with a `push` method works as a `Notifier` without any import from this package.
- **Body is truncated by ntfy.sh to ~4096 bytes.** Callers are responsible for keeping
  `body` short (a notification preview, not the full message). `NativeAppInterface` already
  truncates to 200 chars in Phase 40's spec — keep that.
- **`ze://` scheme must be registered in the Flutter app.** This is a Phase 43 concern.
  Until the Flutter app exists, the `X-Click` header is ignored. ntfy gracefully ignores
  unknown URL schemes — no error is produced.
- **Topic should be non-guessable.** ntfy.sh topics are effectively public if known.
  Even with a token, a random suffix prevents accidental topic collision with other users.
  Generate once at setup: `ze-$(openssl rand -hex 8)`.

---

## Testing

| Test | Location |
|------|----------|
| `NtfyNotifier.push()` sends correct headers (title, priority, tags) | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` includes `Authorization` header when token set | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` omits `Authorization` when no token | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` sets `X-Click` with encoded deep link when `data` set | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` omits `X-Click` when `data` is None | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` swallows HTTP 4xx/5xx without raising | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.push()` swallows connection errors without raising | `tests/notifications/test_ntfy.py` |
| `NtfyNotifier.__init__` raises `ValueError` when ntfy.sh + no token | `tests/notifications/test_ntfy.py` |
| `_encode_deep_link` produces valid `ze://navigate?...` URL | `tests/notifications/test_ntfy.py` |
| `NativeAppInterface` accepts any `Notifier` (mock satisfies Protocol) | `tests/interface/test_native.py` |

---

## Open Questions

- [x] **Should `ze-notifications` raise `ZeConfigError` or `ValueError` at startup?**
  → `ValueError`. `ze-notifications` has no ze deps. The container (`ze/`) can wrap it
  in a `ZeConfigError` if desired, but the package itself stays dep-free.
- [x] **One topic or multiple (per-priority, per-type)?** → One topic per Ze instance.
  ntfy supports priority and tags for visual differentiation within a single topic.
  Multiple topics adds operational complexity for no user benefit.
- [ ] **Should the deep link scheme be configurable?** `ze://` is hardcoded in
  `_encode_deep_link`. If the Flutter app ever needs a different scheme (e.g. for
  App Store distribution with a registered URL scheme), this becomes a config value.
  Defer until the Flutter app spec clarifies.
