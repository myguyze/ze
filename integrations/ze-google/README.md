# ze-google

Shared Google OAuth2 credentials for Ze. Provides authenticated service client factories for Google APIs — no Ze framework dependencies.

## Responsibilities

| Module | What it provides |
|---|---|
| `auth.py` | `GoogleCredentials`, `SCOPES`, service client factories (`build_calendar_service`, `build_gmail_service`) |

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
calendar = creds.build_calendar_service()
gmail = creds.build_gmail_service()
```

Credentials are wired into the container in `ze-api` and injected into `ze-calendar` and the Gmail channel.

## Setup

Run the one-time OAuth2 flow from the repo root:

```bash
make google-auth
```

This writes a refresh token to `.env`.
