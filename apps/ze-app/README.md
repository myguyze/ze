# ze-app

Flutter client for Ze. Native app for iOS, Android, macOS, and web that connects to `ze-api` over WebSocket and receives proactive notifications via ntfy.

## Stack

| Layer | Technology |
|---|---|
| Framework | Flutter 3.22+ / Dart 3.3+ |
| State | flutter_riverpod |
| Transport | WebSocket (`web_socket_channel`) |
| Navigation | go_router |
| Push (deep links) | uni_links |
| Storage | flutter_secure_storage |
| Rendering | flutter_markdown |

## Structure

```
lib/
├── main.dart
├── app.dart
└── src/
    ├── components/   # Server-driven component renderers
    ├── config/       # App configuration
    ├── messages/     # Message list, chat UI
    ├── navigation/   # Route definitions (go_router)
    ├── overlay/      # Confirmation overlays, gates
    ├── screens/      # Top-level screens
    └── ws/           # WebSocket client, connection state
```

## Connection

The app connects to `ze-api` at `ws://<host>/ws` using the `ZE_API_KEY` as a bearer token. On reconnect, the server replays any unread messages.

Push notifications arrive via ntfy and carry deep-link data (`ze://navigate?...`) that the app handles via `uni_links`.

## Getting started

```bash
cd apps/ze-app
flutter pub get
flutter run
```

Configure the API host and key in the app settings screen on first launch.
