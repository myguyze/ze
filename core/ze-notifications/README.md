# ze-notifications

Push notification abstraction for Ze. Decouples notification delivery from the rest of the system — currently implemented via [ntfy](https://ntfy.sh).

## Role in Ze

When the user is away from the web app, Ze still needs to reach them — morning briefings, calendar reminders, stuck goal alerts, correlation insights. `ze-notifications` abstracts push delivery so the rest of the system doesn't depend on a specific provider.

### Key features

- `Notifier` protocol — swappable delivery backend
- `NtfyNotifier` — HTTP push via ntfy with priority, tags, and deep-link data
- Priority levels from silent background sync to urgent alerts

### Integration

`NtfyNotifier` is constructed in `ze-api`'s lifespan and injected into `ProactiveNotifier` and `NativeAppInterface`. When the WebSocket is disconnected, outbound messages fall back to ntfy push; when connected, they flow over WebSocket instead.

## Responsibilities

| Module | What it provides |
|---|---|
| `notifier.py` | `Notifier` Protocol — the interface all delivery backends must satisfy |
| `ntfy.py` | `NtfyNotifier` — delivers notifications via ntfy HTTP API |
| `types.py` | `Notification` dataclass with priority, tags, and deep-link `data` |

## Dependencies

No Ze package dependencies. Depends only on: `aiohttp`.

## Usage

```python
from ze_notifications.ntfy import NtfyConfig, NtfyNotifier
from ze_notifications.types import Notification

config = NtfyConfig(base_url="https://ntfy.sh", topic="ze-abc123", token="...")
notifier = NtfyNotifier(config, session)

await notifier.push(Notification(
    title="Morning briefing",
    body="Here's your day...",
    priority=3,
    data={"navigate": "briefing"},
))
```

The React web app (`ze-web`) uses browser URL routing for in-app navigation. ntfy push notifications alert the user when the app is closed; tapping opens the app in the browser.

## Configuration

| Variable | Description |
|---|---|
| `NTFY_BASE_URL` | ntfy server URL (e.g. `https://ntfy.sh`) |
| `NTFY_TOPIC` | Your topic name — keep non-guessable for ntfy.sh |
| `NTFY_TOKEN` | Bearer token; required for ntfy.sh topics |

## Notification priorities

| Value | Meaning |
|---|---|
| 1 | min — silent background sync |
| 2 | low |
| 3 | default |
| 4 | high |
| 5 | urgent — stuck goals, critical alerts |

## Testing

From the repo root:

```bash
make test-notifications
```

See [docs/testing.md](../../docs/testing.md).
