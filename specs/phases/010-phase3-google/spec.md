# Phase 3 — Google Calendar & Gmail Spec

## Purpose

Add `calendar` and `email` agents backed by Google Calendar API and Gmail API.
Both agents share a single OAuth2 credential object built from Fly.io secrets.
No custom token refresh logic — the official `google-auth` library handles it.

## New Dependencies

```toml
"google-api-python-client>=2.0"   # Calendar + Gmail service clients
"google-auth>=2.0"                 # Credentials, token refresh
"google-auth-oauthlib>=1.0"        # InstalledAppFlow for one-time auth script
```

Add to `pyproject.toml` `[project.dependencies]`.

The Google API client (`googleapiclient.discovery.build`) is synchronous.
All tool calls that hit Google APIs must be wrapped with `asyncio.to_thread()`
to avoid blocking the event loop.

---

## OAuth2 Setup

### Required environment variables

```
GOOGLE_CLIENT_ID=...        # from Google Cloud Console
GOOGLE_CLIENT_SECRET=...    # from Google Cloud Console
GOOGLE_REFRESH_TOKEN=...    # from one-time auth script below
```

Add to `.env.example`. In production, set as Fly.io secrets.

### One-time auth script: `scripts/google_auth.py`

Run once locally to obtain the refresh token. Requires a `client_secrets.json`
downloaded from Google Cloud Console (OAuth 2.0 Client ID, Desktop app type).

```python
#!/usr/bin/env python
"""Run once to get a Google refresh token. Output: fly secrets set command."""

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
creds = flow.run_local_server(port=0)

print("\nRun the following command to store the token in Fly.io:")
print(f"fly secrets set GOOGLE_REFRESH_TOKEN={creds.refresh_token}")
```

**Usage:**
```bash
python scripts/google_auth.py
# opens browser → authorise → prints fly command → run it
```

`client_secrets.json` is never committed. The refresh token is long-lived and
does not expire unless explicitly revoked in Google Account settings.

### Google Cloud Console setup (one-time)

1. Create a project at console.cloud.google.com.
2. Enable **Google Calendar API** and **Gmail API**.
3. Create OAuth 2.0 credentials → Desktop app → download `client_secrets.json`.
4. Add your Google account email as a test user (while app is in testing mode).

---

## `ze/google/` Package

Shared Google infrastructure used by both agents. Not agent-specific.

```
ze/google/
├── __init__.py
└── auth.py      # GoogleCredentials — credential object + service factories
```

### `ze/google/auth.py`

```python
import asyncio
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",
]

TOKEN_URI = "https://oauth2.googleapis.com/token"


class GoogleCredentials:
    """Wraps a Google OAuth2 refresh token and provides service client factories.

    The underlying Credentials object refreshes the access token automatically
    when it expires — no manual refresh logic needed.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
    ) -> None:
        self._creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )

    def calendar(self):
        """Return a Google Calendar API v3 service client."""
        return build("calendar", "v3", credentials=self._creds)

    def gmail(self):
        """Return a Gmail API v1 service client."""
        return build("gmail", "v1", credentials=self._creds)

    @classmethod
    def from_settings(cls, settings) -> "GoogleCredentials | None":
        """Return None if any required credential env var is unset."""
        if not all([
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_refresh_token,
        ]):
            return None
        return cls(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            refresh_token=settings.google_refresh_token,
        )
```

`from_settings()` returns `None` when credentials are absent. Bootstrap skips
agents that declare `GoogleCredentials` as a dep when it is `None` in `_dep_map`
— they remain disabled without crashing startup.

---

## Settings Additions

`ze/settings.py`:

```python
# ── Google OAuth2 ─────────────────────────────────────────────────────────────
google_client_id: str = ""
google_client_secret: str = ""
google_refresh_token: str = ""
```

---

## Calendar Agent

### Module structure

```
ze/agents/calendar/
├── __init__.py      # no agent-specific tools to register
├── agent.py         # _AGENT_INSTRUCTIONS constant + @register CalendarAgent
└── tools.py         # list_events, create_event, update_event, delete_event
```

### Tools — `ze/agents/calendar/tools.py`

All Google API calls use `asyncio.to_thread()` since `googleapiclient` is sync.

```python
from ze.agents.tool import ToolAccess, tool
from ze.google.auth import GoogleCredentials

@tool(access=ToolAccess.READ, description="List upcoming Google Calendar events.")
async def list_events(
    credentials: GoogleCredentials,
    calendar_id: str = "primary",
    max_results: int = 10,
    query: str = "",
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Create a new Google Calendar event.")
async def create_event(
    credentials: GoogleCredentials,
    summary: str,
    start: str,   # ISO 8601: "2025-06-01T10:00:00+01:00"
    end: str,     # ISO 8601: "2025-06-01T11:00:00+01:00"
    description: str = "",
    location: str = "",
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Update an existing Google Calendar event.")
async def update_event(
    credentials: GoogleCredentials,
    event_id: str,
    summary: str | None = None,
    start: str | None = None,
    end: str | None = None,
    description: str | None = None,
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Delete a Google Calendar event.")
async def delete_event(
    credentials: GoogleCredentials,
    event_id: str,
    calendar_id: str = "primary",
) -> ToolCall: ...
```

`start` and `end` are ISO 8601 strings. The LLM is expected to produce them;
the system prompt instructs the model to use the correct format and timezone.

### Agent — `ze/agents/calendar/agent.py`

```python
@register
class CalendarAgent(BaseAgent):
    name  = "calendar"
    tools = ["list_events", "create_event", "update_event", "delete_event"]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        google_credentials: GoogleCredentials,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._google = google_credentials
```

The agent interprets the user's prompt and decides which tool to call.
For write operations, `call_tool()` enforces draft/confirm via gate decision.

### Config — `config/agents/calendar.yaml`

```yaml
enabled: true
description: |
  Manages Google Calendar events. Use for reading, creating, updating, or
  deleting calendar events, checking availability, or scheduling.
model: anthropic/claude-haiku-4-5
timeout: 30
intent_map:
  read:   "Read or list calendar events."
  create: "Create a new calendar event."
  update: "Update or reschedule an existing event."
  delete: "Delete or cancel a calendar event."
```

### Capabilities — `config/capabilities.yaml` additions

```yaml
calendar:
  enabled: true
  read:   autonomous
  create: confirm
  update: confirm
  delete: confirm
```

---

## Email Agent

### Module structure

```
ze/agents/email/
├── __init__.py
├── agent.py         # _AGENT_INSTRUCTIONS constant + @register EmailAgent
└── tools.py         # list_emails, get_email, draft_email, send_email, archive_email
```

### Tools — `ze/agents/email/tools.py`

```python
@tool(access=ToolAccess.READ, description="List recent Gmail messages matching a query.")
async def list_emails(
    credentials: GoogleCredentials,
    query: str = "",
    max_results: int = 10,
) -> ToolCall: ...

@tool(access=ToolAccess.READ, description="Get the full content of a Gmail message by ID.")
async def get_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Create a Gmail draft without sending.")
async def draft_email(
    credentials: GoogleCredentials,
    to: str,
    subject: str,
    body: str,
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Send an email via Gmail.")
async def send_email(
    credentials: GoogleCredentials,
    to: str,
    subject: str,
    body: str,
) -> ToolCall: ...

@tool(access=ToolAccess.WRITE, description="Archive a Gmail message (remove from inbox).")
async def archive_email(
    credentials: GoogleCredentials,
    message_id: str,
) -> ToolCall: ...
```

Hard delete is not supported — `archive_email` removes the INBOX label only.

### Agent — `ze/agents/email/agent.py`

```python
@register
class EmailAgent(BaseAgent):
    name  = "email"
    tools = ["list_emails", "get_email", "draft_email", "send_email", "archive_email"]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        google_credentials: GoogleCredentials,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._google = google_credentials
```

### Config — `config/agents/email.yaml`

```yaml
enabled: true
description: |
  Manages Gmail. Use for reading emails, drafting replies, sending messages,
  or archiving conversations.
model: anthropic/claude-haiku-4-5
timeout: 30
intent_map:
  read:   "Read or list emails."
  create: "Draft or send an email."
  delete: "Archive an email thread."
```

### Capabilities — `config/capabilities.yaml` additions

```yaml
email:
  enabled: true
  read:   autonomous
  create: draft_only    # send_email only fires after user confirms via gate
  delete: confirm
```

---

## Container Wiring

`ze/container.py` — add before `bootstrap_agents()`:

```python
from ze.google.auth import GoogleCredentials

google_credentials = GoogleCredentials.from_settings(settings)
if google_credentials:
    from ze.agents.bootstrap import _dep_map
    _dep_map[GoogleCredentials] = google_credentials
    log.info("google_credentials_loaded")
else:
    log.info("google_credentials_absent", detail="calendar and email agents will be skipped")
```

When `google_credentials` is `None`, `GoogleCredentials` is absent from `_dep_map`.
The bootstrap resolver raises `AgentConfigError` when it tries to instantiate
`CalendarAgent` or `EmailAgent` — to prevent this, `enabled: false` in their YAML
should be the default until credentials are available.

**Safer approach**: set `enabled: false` in `config/agents/calendar.yaml` and
`config/agents/email.yaml` by default. Change to `enabled: true` only after
`GOOGLE_REFRESH_TOKEN` is set. The `_dep_map` check is a secondary safety net.

---

## `.env.example` Additions

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
```

---

## asyncio.to_thread Pattern

Every tool function that calls a Google API service must use `asyncio.to_thread`:

```python
@tool(access=ToolAccess.READ, description="List upcoming Google Calendar events.")
async def list_events(
    credentials: GoogleCredentials,
    calendar_id: str = "primary",
    max_results: int = 10,
    query: str = "",
) -> ToolCall:
    start = time.monotonic()
    try:
        service = credentials.calendar()
        now = datetime.utcnow().isoformat() + "Z"

        result = await asyncio.to_thread(
            lambda: service.events().list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                q=query or None,
            ).execute()
        )

        events = result.get("items", [])
        duration_ms = int((time.monotonic() - start) * 1000)
        return ToolCall(
            tool_name="list_events",
            args={"calendar_id": calendar_id, "max_results": max_results, "query": query},
            result=events,
            duration_ms=duration_ms,
            success=True,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning("list_events_failed", error=str(exc))
        return ToolCall(
            tool_name="list_events",
            args={},
            result=None,
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
        )
```

All tools follow this exact pattern: `asyncio.to_thread` wrapping the sync
Google API call, timing, try/except returning a failed `ToolCall` on error.

---

## File Additions Summary

| File | Action |
|---|---|
| `scripts/google_auth.py` | New — one-time OAuth2 flow |
| `ze/google/__init__.py` | New |
| `ze/google/auth.py` | New — `GoogleCredentials` |
| `ze/agents/calendar/__init__.py` | Update — import tools |
| `ze/agents/calendar/agent.py` | New |
| `ze/agents/calendar/agent.py` | `_AGENT_INSTRUCTIONS` defined inline |
| `ze/agents/calendar/tools.py` | New |
| `ze/agents/email/__init__.py` | Update — import tools |
| `ze/agents/email/agent.py` | New |
| `ze/agents/email/agent.py` | `_AGENT_INSTRUCTIONS` defined inline |
| `ze/agents/email/tools.py` | New |
| `ze/settings.py` | Add 3 Google env vars |
| `ze/container.py` | Wire `GoogleCredentials` before bootstrap |
| `config/agents/calendar.yaml` | Update — set `enabled: true`, add intent_map |
| `config/agents/email.yaml` | Update — set `enabled: true`, add intent_map |
| `config/capabilities.yaml` | Update — calendar + email entries |
| `pyproject.toml` | Add 3 Google dependencies |
| `.env.example` | Add 3 Google env vars |

---

## Open Questions

- [x] **Timezone handling** — `TIMEZONE` env var (e.g. `Europe/Lisbon`). Injected
  into the calendar agent system prompt so the LLM produces correct ISO 8601
  datetimes. Single-user system — one timezone, zero API calls.
- [x] **Gmail body format** — plain text only for Phase 3. HTML deferred to Phase 4.
- [ ] **Email threading** — `send_email` creates a new thread. Reply-to-thread
  support (passing `threadId`) is deferred to Phase 4.
