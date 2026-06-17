# ze-google

Shared Google OAuth2 credentials for Ze. Provides authenticated service client factories for Google APIs — no Ze framework dependencies.

## Role in Ze

Google Calendar and Gmail are the two primary external services Ze integrates with. `ze-google` wraps OAuth2 refresh-token credentials and exposes typed client factories so plugins never handle token refresh or scope management themselves.

### Key features

- Single refresh token covers Calendar and Gmail scopes
- Automatic access-token refresh — no manual token management
- `from_settings()` factory — returns `None` when env vars are absent (graceful disable)

### Integration

Satisfies the `ZeIntegration` protocol structurally. Plugins declare `GoogleCredentials` in `integration_types()`; `ze-api` bootstrap calls `from_settings` once and injects the result into `EmailPlugin` and `CalendarPlugin`. Credentials are obtained once via `make google-auth`.

## Responsibilities

| Module | What it provides |
|---|---|
| `auth.py` | `GoogleCredentials`, `SCOPES`, `calendar()` and `gmail()` client factories |

## Dependencies

No Ze package dependencies. Depends only on: `google-auth`, `google-api-python-client`.

## Usage

```python
from ze_google.auth import GoogleCredentials

creds = GoogleCredentials(
    client_id=...,
    client_secret=...,
    refresh_token=...,
)
calendar = creds.calendar()
gmail = creds.gmail()
```

Credentials are wired into the container in `ze-api` and injected into `ze-calendar` and the Gmail channel.

## Setup

Run the one-time OAuth2 flow from the repo root:

```bash
make google-auth
```

This writes a refresh token to `.env`.

## Testing

From the repo root:

```bash
make test-google
```

See [docs/testing.md](../../docs/testing.md).
