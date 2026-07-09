# Spec 26 — Prospecting Agent

## Implementation Status

| Feature | Status |
|---------|--------|
| `ze-browser` sidecar service (Playwright + FastAPI) | ✅ Done |
| `ze-browser` Python package — `BrowserClient` (`httpx`) | ✅ Done |
| `browser_extract` tool — with stealth + rate limiting | ✅ Done |
| `add_prospect` tool | ✅ Done |
| `draft_outreach` tool — WRITE, saves draft to DB directly | ✅ Done |
| `log_outreach_event` tool | ✅ Done |
| Migration 014 — `prospect_campaigns` + `prospect_outreach` tables | ✅ Done |
| `BaseAgent.agentic_loop()` — `max_history_tokens` param | ✅ Done |
| `ProspectingAgent` — agentic research loop with token budget | ✅ Done |
| Stale campaign recovery — startup + cron check | ✅ Done |
| Companion wiring — `log_outreach_event` tool | ✅ Done |
| Container wiring + config | ✅ Done |
| `ze-browser` Fly.io deployment config | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze autonomously builds target lists, enriches contact details from web sources,
and generates outreach materials. The user sets a goal ("find 10 charter operators
in Portugal"); Ze does the research, adds contacts, and produces whatever output
was requested — all without user confirmation at each step.

This is the first fully autonomous multi-step workflow in Ze and the foundation for
the prospecting-to-close pipeline described in `VISION.md`.

---

## Out of Scope

- Sending emails or messages directly (Ze drafts; the user sends).
- LinkedIn login (public profiles only, found via Google + browser).
- Campaign editing or re-running (new brief → new campaign).
- Deduplication across campaigns (handled naturally by `PersonStore.get_by_name()`).
- Paid data enrichment APIs (Clay, Apollo, Hunter) — added later if OSINT falls short.

---

## Repository Layout

```
packages/
├── ze-browser/                 # installable Python package (httpx client)
│   ├── pyproject.toml
│   ├── ze_browser/
│   │   ├── client.py           # BrowserClient
│   │   ├── types.py            # BrowserResult
│   │   └── errors.py           # BrowserError
│   └── tests/
│       └── test_browser_client.py
└── ze/
    ├── ze/
    │   ├── agents/prospecting/
    │   │   ├── __init__.py
    │   │   └── agent.py
    │   └── tools/
    │       ├── browser.py      # browser_extract (imports ze_browser)
    │       └── prospecting.py  # add_prospect, draft_outreach, log_outreach_event
    └── migrations/versions/
        └── 014_prospecting.py

sidecar/browser/                # Fly.io sidecar (separate deploy)
├── main.py
├── extractor.py
├── Dockerfile
├── requirements.txt
└── fly.toml
```

Ze declares `ze-browser` as a workspace dependency in `packages/ze/pyproject.toml`.
The sidecar HTTP service is **not** part of the Python package — it is deployed
independently and called at `settings.browser_service_url`.

---

## `ze-browser` Sidecar Service

A minimal FastAPI + Playwright app deployed as a separate Fly.io app in the same
organisation. Ze calls it over Fly's private network at
`http://ze-browser.internal:8080` — never exposed publicly.

### Anti-bot Measures

Sites actively block headless browsers. The service must use:

- **`playwright-stealth`** — patches browser fingerprint (navigator properties, WebGL,
  canvas) to match a real Chrome install.
- **Random user-agent rotation** — pick from a maintained list of recent Chrome
  user-agents on every request.
- **Random pre-action delay** — 1–3s jitter before starting navigation, simulating
  human timing.

When a page returns a CAPTCHA, login wall, or empty body (< 200 chars), the service
returns `status_code: 403` and an empty `text`. The tool layer handles this as a
graceful miss — the LLM moves to the next source.

### API

```
POST /extract
  Body: {url: str, timeout_ms: int = 15000}
  Returns: {url: str, title: str, text: str, status_code: int}
  Errors: 400 if URL invalid; 504 if timeout; 502 if navigation fails; 403 if blocked
```

The service navigates to `url`, waits for `networkidle` with a `domcontentloaded`
fallback for SPA-heavy pages, then extracts visible text via `page.inner_text("body")`.
Falls back to `page.content()` stripped of tags if `inner_text` returns < 200 chars.
No LLM call inside the service — Ze's LLM decides what to do with the text.

```
GET /health
  Returns: {status: "ok"}
```

### Dockerfile

Base image: `mcr.microsoft.com/playwright/python:v1.44.0-jammy`.
Install `fastapi`, `uvicorn`, `playwright-stealth`. `playwright install chromium --with-deps`
baked into the image build.

Launch with `--no-sandbox` Chromium flag (required in containers).

### `fly.toml` (ze-browser)

```toml
app = "ze-browser"
primary_region = "iad"          # must match ze app region

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8080
  force_https = false            # private network only, no TLS needed
  auto_stop_machines = "stop"
  auto_start_machines = true
  min_machines_running = 1       # avoid cold-start delay on first browser call

[[vm]]
  size = "shared-cpu-1x"
  memory = "1gb"                 # Chromium needs ~512MB headroom
```

`min_machines_running = 1` keeps one machine warm. At Fly's pricing (~$5/month for
a shared-cpu-1x) this is negligible for a single-user app and avoids 30–60s cold
start on first browser call.

Both `ze` and `ze-browser` must be deployed to the **same Fly region** to keep
private network latency under 5ms.

### Deployment Workflow

`ze-browser` is a separate Fly app with its own deploy. Until a CI pipeline exists,
deploy manually:

```bash
cd ze-browser
fly deploy                       # first time: fly launch --no-deploy first
fly logs                         # verify service started
```

Ze's deploy does not trigger `ze-browser`'s deploy — they are versioned independently.
The API contract between them is the `/extract` endpoint; breaking changes must be
coordinated manually.

---

## `BrowserClient` (`packages/ze-browser/ze_browser/client.py`)

Installable package `ze-browser`. Import as:

```python
from ze_browser import BrowserClient, BrowserError, BrowserResult
```

Uses `httpx` (declared in `ze-browser`'s `pyproject.toml`; Ze re-exports via workspace dep).

```python
@dataclass
class BrowserResult:
    url: str
    title: str
    text: str
    status_code: int


class BrowserClient:
    def __init__(self, base_url: str, timeout: int = 20) -> None:
        # base_url from settings.browser_service_url
        # timeout in seconds — covers network round-trip + page render

    async def extract(self, url: str) -> BrowserResult:
        """Navigate to url and return visible page text."""
```

Raises `BrowserError` on connection error or HTTP 5xx so agents can handle
gracefully. HTTP 403 (blocked) is returned as a valid `BrowserResult` with empty
`text` — not an exception.

---

## Database Schema

Migration `migrations/versions/014_prospecting.py`.

```sql
CREATE TABLE prospect_campaigns (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    brief        TEXT        NOT NULL,
    status       TEXT        NOT NULL DEFAULT 'running',  -- running | complete | failed
    target_count INT,
    found_count  INT         NOT NULL DEFAULT 0,
    output       TEXT,       -- generated summary / report Ze produced
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE prospect_outreach (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID        REFERENCES prospect_campaigns(id) ON DELETE CASCADE,  -- NULL for manual logs
    contact_id  UUID        NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    channel     TEXT        NOT NULL,  -- email | linkedin | sms | phone | other
    status      TEXT        NOT NULL DEFAULT 'pending',  -- pending | sent | replied | no_reply | bounced
    draft       TEXT,       -- outreach draft if Ze generated one
    sent_at     TIMESTAMPTZ,
    replied_at  TIMESTAMPTZ,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(campaign_id, contact_id)
);

CREATE INDEX prospect_campaigns_status_idx ON prospect_campaigns(status, created_at DESC);
CREATE INDEX prospect_outreach_campaign_idx ON prospect_outreach(campaign_id);
CREATE INDEX prospect_outreach_contact_idx  ON prospect_outreach(contact_id);
CREATE INDEX prospect_outreach_status_idx   ON prospect_outreach(status, created_at DESC);
```

`campaign_id` is nullable in `prospect_outreach` to support standalone outreach
events the user reports for contacts Ze didn't prospect (e.g. "I called João, who
I met at a conference").

---

## Tools (`ze/tools/`)

### `browser.py` — `browser_extract`

```python
@tool(access=ToolAccess.READ, description=(
    "Navigate to a URL and return its visible text content. "
    "Returns an error string if the page is blocked or unreachable — "
    "in that case, skip this URL and try another source."
))
async def browser_extract(
    url: str,
    browser_client: BrowserClient,   # Ze-internal dep, injected by agentic_loop
    settings: Settings,              # Ze-internal dep
) -> ToolCall:
```

Calls `BrowserClient.extract(url)`. Returns `result.text` truncated to
`settings.browser_max_text_chars` (default 8 000). If `result.text` is empty
or `result.status_code == 403`, returns the string `"[blocked or empty — skip this URL]"`.

**Rate limiting:** `browser_extract` sleeps for `settings.browser_delay_ms`
(default `2000`) milliseconds before each call. This is enforced inside the tool,
not by the caller, so the LLM cannot bypass it.

### `prospecting.py` — `add_prospect`

```python
@tool(access=ToolAccess.WRITE, description=(
    "Add a prospective contact found during research. "
    "Sets confirmed=False and source_type='research'. "
    "Call once per person found — deduplication is automatic."
))
async def add_prospect(
    name: str,
    company: str | None,
    role: str | None,
    relationship: str,          # "charter operator, found via ANAC registry"
    contact_info: dict,         # {"email": "...", "linkedin": "..."}
    source_url: str,            # where Ze found this person
    enrichment_notes: str,      # what Ze found, what's missing — surfaces quality
    campaign_id: str,
    person_store: PersonStore,
    pool: asyncpg.Pool,
) -> ToolCall:
```

Creates a `Person` with `confirmed=False`, `source_type="research"`, `confidence=0.2`.
Stores `enrichment_notes` in `Person.notes`. Inserts a `prospect_outreach` row
(`status="pending"`). Deduplicates via `PersonStore.get_by_name()`.

The `enrichment_notes` field ("found email and LinkedIn; no phone; company website
unresponsive") is surfaced in Ze's final summary so the user knows which prospects
are well-enriched vs sparse.

### `prospecting.py` — `draft_outreach`

```python
@tool(access=ToolAccess.WRITE, description=(
    "Draft a personalised outreach message for a prospect and save it."
))
async def draft_outreach(
    name: str,
    context: str,               # what Ze knows about this person
    campaign_brief: str,        # the user's original prospecting goal
    channel: str,               # "email" | "linkedin" | other
    campaign_id: str,           # Ze-internal dep — injected by agentic_loop
    client: OpenRouterClient,   # Ze-internal dep
    model: str,                 # Ze-internal dep
    person_store: PersonStore,  # Ze-internal dep
    pool: asyncpg.Pool,         # Ze-internal dep
) -> ToolCall:
```

Calls the LLM to generate the draft, then immediately writes it to
`prospect_outreach.draft` for the matching `(campaign_id, contact_id)` row.
Looks up `contact_id` via `PersonStore.get_by_name(name)`. Returns the draft
string in `ToolCall.result` so the LLM can include it in the final summary.

The tool does its own DB write so the agent never needs to handle individual tool
results mid-loop — `agentic_loop` only surfaces the final accumulated list.

### `prospecting.py` — `log_outreach_event`

```python
@tool(access=ToolAccess.WRITE, description=(
    "Record that the user sent a message to a prospect or received a reply. "
    "Call when the user explicitly mentions contacting someone or getting a response."
))
async def log_outreach_event(
    contact_name: str,
    event_type: str,            # "sent" | "replied" | "no_reply" | "bounced"
    channel: str,               # "email" | "linkedin" | "sms" | "phone" | "other"
    notes: str,
    pool: asyncpg.Pool,
    person_store: PersonStore,
) -> ToolCall:
```

Looks up the contact by name via `PersonStore.get_by_name()`, finds the most
recent `prospect_outreach` row, and updates its status + timestamp. If no outreach
row exists, creates a standalone record with `campaign_id=NULL`.

**Entity resolution:** if `get_by_name()` returns multiple matches, the tool picks
the one with the most recent `last_mentioned`. If this is ambiguous (multiple contacts
with similar names), the tool returns a message like `"Ambiguous: found João Silva and
João Santos — please clarify"` and makes no write. The companion surfaces this to the user.

**Extraction reliability note:** Passive extraction from conversation text will miss
casual phrasing ("had a call with the charter guy"). The companion's tool description
explicitly limits extraction to cases where the user **explicitly mentions** contacting
someone. Users can also trigger logging directly:
```
"log that I sent João an email yesterday"
"mark Maria as replied on LinkedIn"
```
These explicit phrasings are reliable; casual references may be missed — that is
acceptable.

---

## `ProspectingAgent` (`ze/agents/prospecting/agent.py`)

```python
@register
class ProspectingAgent(BaseAgent):
    name = "prospecting"
    tools = [
        "web_search",
        "browser_extract",
        "add_prospect",
        "draft_outreach",
    ]
```

Uses `agentic_loop()` — the LLM drives the research sequence.

### Token Budget

Each `browser_extract` call can add 8 000 chars (~2 000 tokens) to the message
history. With 15 iterations, history could exceed 30 000 tokens before the LLM
context limit is hit.

Truncation must happen **per-iteration inside `agentic_loop`**, not before it —
the loop mutates the messages list as it runs, so pre-call truncation has no effect
after the first iteration.

**`BaseAgent.agentic_loop()` gains a new optional parameter:**

```python
async def agentic_loop(
    self,
    ...
    max_iterations: int = 6,
    max_history_tokens: int | None = None,   # NEW — truncate oldest tool results
) -> tuple[str, list[ToolCall]]:
```

When `max_history_tokens` is set, at the start of each iteration Ze counts the
approximate tokens in the current `messages` list (`len(text) // 4` per message).
If the total exceeds the budget, it removes the oldest `role="tool"` messages one
by one until under budget. The system prompt and the most recent 4 messages are
never removed.

`ProspectingAgent.run()` passes `max_history_tokens=settings.prospecting_max_loop_tokens`
to `agentic_loop()`. No other agent is affected — the param defaults to `None`
(no truncation), preserving existing behaviour.

### System Prompt

```
_AGENT_INSTRUCTIONS = """\
You are Ze's prospecting engine. Given a brief, you autonomously:
1. Research candidates matching the target profile using the tools below.
2. Enrich each candidate: name, role, company, email, LinkedIn URL.
3. Add each via add_prospect — include enrichment_notes summarising what you found
   and what's missing. This surfaces quality to the user.
4. Generate the output the user requested (summary, draft outreach, or both).

Research strategy — work through sources in this priority order:
- web_search: identify companies in the target space, then find people at those companies
- browser_extract on company websites: team/about pages often list names and roles
- browser_extract on government/industry registries: ANAC (aviation), RNPC (companies),
  sector-specific databases — search for these via web_search first
- LinkedIn public profiles: Google "site:linkedin.com/in [name] [title] [country]",
  then browser_extract the result URL

If browser_extract returns "[blocked or empty]", move to the next source immediately.
Do not retry the same URL more than once.

Stop when you reach the requested count or have exhausted reasonable sources.

Final output format:
- Summary: for each prospect — name, company, role, contact info found, and a one-line
  enrichment note ("email found", "LinkedIn only", "name and company only — sparse").
- Drafts (if requested): one message per prospect after the summary.
\
"""
```

### `run()` Flow

1. Create a `prospect_campaigns` row (`status="running"`).
2. Warm up `ze-browser` by calling `browser_client.health()` (fast GET /health); if
   unreachable, log warning and proceed — Ze falls back to Tavily-only research.
3. Build system prompt, call `agentic_loop()` with
   `max_iterations=settings.prospecting_max_iterations` and
   `max_history_tokens=settings.prospecting_max_loop_tokens`.
4. Update campaign: `status="complete"`, `found_count`, `output=response`, `completed_at`.
5. Return `AgentResult`.

On any unhandled exception: update campaign to `status="failed"`, re-raise.

`deps` passed to `agentic_loop`:
```python
{
    "browser_client": browser_client,
    "person_store": person_store,
    "pool": pool,
    "client": openrouter_client,
    "model": self._model(ctx),
    "settings": self._settings,
    "campaign_id": str(campaign_id),
}
```

### Stale Campaign Recovery

At app startup and on a nightly cron, Ze scans for campaigns with
`status = 'running'` and `created_at < NOW() - INTERVAL '{timeout} minutes'`
(default 60 minutes) and marks them `failed`. This prevents stuck campaigns from
accumulating after crashes.

```python
async def recover_stale_campaigns(pool: asyncpg.Pool, timeout_minutes: int = 60) -> None:
    await pool.execute(
        """
        UPDATE prospect_campaigns
        SET status = 'failed', completed_at = NOW()
        WHERE status = 'running'
          AND created_at < NOW() - ($1 * INTERVAL '1 minute')
        """,
        timeout_minutes,
    )
```

Called in `build_container()` lifespan after pool creation, and scheduled as a
nightly cron job.

---

## Output and Telegram Limits

Telegram messages are capped at 4 096 characters. A summary of 10 enriched
prospects with outreach drafts easily exceeds this. Ze's response is chunked:

- The agent produces a single `response` string.
- `ZeBot` (in `ze/telegram/bot.py`) splits messages longer than 4 000 chars on
  paragraph boundaries (`\n\n`) before sending. This is already implemented in the
  existing message formatter — no change needed here.
- Outreach drafts are appended after the prospect summary, separated by `---`.

---

## Unconfirmed Contacts UX

Research-sourced prospects are added with `confirmed=False`, so they don't appear
in `/contacts` (which defaults to `confirmed_only=True`). The user sees them via:

1. **Campaign output** — Ze's immediate response lists every prospect found with
   name, role, contact info, and enrichment quality. This is the primary interface.
2. **Confirmation prompts** — The existing `ContactReviewNotifier` cron surfaces
   unconfirmed contacts for review, including research-sourced ones.
3. **`/contacts` with query** — `PersonStore.search(confirmed_only=False)` is used
   when a search term is provided, so `/contacts charter` will show unconfirmed
   prospects matching "charter".

A `/campaigns` Telegram command (list past campaigns with prospect counts) is
a natural fast-follow but is out of scope for this phase.

---

## Outreach Tracking via Companion

The companion agent runs two parallel post-response extraction calls:
1. `extract_contacts`
2. `log_outreach_event`

User facts are extracted in `write_memory` (see `specs/zc-06-memory.md`).

`log_outreach_event` only fires when the user's message **explicitly mentions**
contacting someone. Casual phrasing ("had a call with the charter guy") is not
extracted — this is acceptable and documented. Users who want reliable logging
use explicit phrasing:
> "log that I sent João an email", "mark Maria as replied on LinkedIn"

---

## Configuration

### `config/config.yaml` additions

```yaml
agents:
  prospecting:
    enabled: true
    model: anthropic/claude-sonnet-4-5
    timeout_seconds: 180
    description: >
      Find people matching a target profile, enrich their contact details, and
      generate outreach materials. Use when the user wants to build a prospect
      list, find contacts in an industry or geography, or prepare outreach for
      a campaign.
    intent_map:
      read: autonomous
      write: autonomous
    capabilities: {}

browser:
  service_url: "http://ze-browser.internal:8080"
  timeout_seconds: 20
  max_text_chars: 8000
  delay_ms: 2000                  # mandatory pause between browser_extract calls

prospecting:
  max_iterations: 15
  max_loop_tokens: 24000          # truncate oldest tool results beyond this
  stale_campaign_timeout_minutes: 60
```

### `Settings` additions

```python
browser_service_url: str = "http://ze-browser.internal:8080"
browser_timeout_seconds: int = 20
browser_max_text_chars: int = 8000
browser_delay_ms: int = 2000

prospecting_max_iterations: int = 15
prospecting_max_loop_tokens: int = 24_000
prospecting_stale_timeout_minutes: int = 60
```

---

## Container Wiring (`packages/ze/ze/container.py`)

```python
from ze_browser import BrowserClient
from ze.agents.prospecting import agent as _  # noqa — registers @register
from ze.proactive.prospecting import recover_stale_campaigns

browser_client = BrowserClient(
    base_url=settings.browser_service_url,
    timeout=settings.browser_timeout_seconds,
)

# At startup, recover any campaigns left running from a previous crash
await recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes)

# Schedule nightly recovery
workflow_scheduler.schedule_job(
    fn=lambda: recover_stale_campaigns(pool, settings.prospecting_stale_timeout_minutes),
    cron="0 3 * * *",
    job_id="recover_stale_campaigns",
)
```

`Container` gains a `browser_client: BrowserClient` field.

---

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| `ze-browser` unreachable at startup | Log warning; Ze proceeds with Tavily-only research |
| `ze-browser` unreachable mid-loop | `browser_extract` returns error string; LLM skips that URL |
| Page blocked / CAPTCHA | `status_code=403`, empty text; tool returns skip message |
| SPA renders empty | Fallback to `page.content()` stripped; if still < 200 chars → skip message |
| Page load timeout | `ze-browser` returns 504; tool returns error string |
| `add_prospect` duplicate | `PersonStore.get_by_name()` deduplicates; source added to existing record |
| `log_outreach_event` ambiguous name | Returns clarification message; no write; companion surfaces to user |
| `agentic_loop` max iterations | Falls back to plain completion summarising found-so-far |
| Token budget exceeded | Oldest tool result messages truncated before next LLM call |
| Campaign crash mid-run | Stale recovery marks `failed` within `stale_campaign_timeout_minutes` |

---

## Testing

Tests live in `packages/ze/tests/agents/prospecting/` and
`packages/ze-browser/tests/`.

| Test | What it verifies |
|------|-----------------|
| `test_browser_client_extract` | Mocked `httpx` → `BrowserResult` returned correctly |
| `test_browser_client_timeout` | `httpx.TimeoutException` → `BrowserError` raised |
| `test_browser_client_403` | 403 response → `BrowserResult` with empty text, no exception |
| `test_browser_extract_tool_rate_limit` | Two calls → sleep called between them |
| `test_browser_extract_tool_truncates` | Page text > `max_text_chars` → truncated in result |
| `test_browser_extract_blocked_returns_skip_msg` | Empty text → skip message string returned |
| `test_add_prospect_new` | New person → `PersonStore.upsert` called, outreach row created |
| `test_add_prospect_duplicate` | Existing person → source added, no duplicate upsert |
| `test_add_prospect_stores_enrichment_notes` | `enrichment_notes` stored in `Person.notes` |
| `test_draft_outreach_tool` | Mocked LLM → draft string returned in `ToolCall.result` |
| `test_log_outreach_event_sent` | Contact name found → outreach row updated to `sent` |
| `test_log_outreach_event_no_match` | Unknown contact → standalone row created with `campaign_id=NULL` |
| `test_log_outreach_event_ambiguous` | Multiple name matches → clarification string, no write |
| `test_prospecting_agent_run` | Mocked agentic loop → campaign created, status `complete` |
| `test_prospecting_agent_failure` | Agentic loop raises → campaign set to `failed` |
| `test_prospecting_agent_browser_unreachable` | Health check fails → runs with Tavily only |
| `test_recover_stale_campaigns` | Old `running` campaign → updated to `failed` |

---

## Open Questions

All resolved.
