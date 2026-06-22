# Ze — Configuration Reference

Ze has three layers of configuration:

- **`.env`** — secrets and deployment-specific values. Never committed.
- **`config/config.yaml`** — all structural and behavioural settings. Committed.
- **`config/persona.yaml`** — persona profiles and dials. Committed.

All files live in `apps/ze-api/config/` (or the path set by `config_dir`).

---

## `.env`

Copy `.env.example` to `.env` and fill in every value before starting the server.

### API keys

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | OpenRouter API key — all LLM calls and web search go through this |
| `ZE_API_KEY` | Yes | Static bearer token for REST endpoints and WebSocket auth |

### Database

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://ze:ze@localhost:5432/ze` | asyncpg connection URL (runtime) |
| `DATABASE_URL_SYNC` | `postgresql+psycopg2://ze:ze@localhost:5432/ze` | psycopg2 URL for Alembic CLI |

### ntfy push notifications

| Variable | Default | Description |
|---|---|---|
| `NTFY_BASE_URL` | `https://ntfy.sh` | ntfy server base URL (use self-hosted URL if applicable) |
| `NTFY_TOPIC` | `""` | ntfy topic name. Leave empty to disable push notifications. |
| `NTFY_TOKEN` | `""` | ntfy authentication token (optional, for private topics) |

### Google (Calendar + Gmail)

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_CLIENT_ID` | If using calendar/email | OAuth2 client ID from Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | If using calendar/email | OAuth2 client secret |
| `GOOGLE_REFRESH_TOKEN` | If using calendar/email | Long-lived refresh token. Obtained by running `scripts/google_auth.py` once locally. |
| `TIMEZONE` | No | IANA timezone string (default: `UTC`). Used for calendar reminders and morning briefing scheduling. |

### Runtime behaviour

| Variable | Default | Description |
|---|---|---|
| `CONFIRM_TIMEOUT_SECONDS` | `900` | How long (seconds) a `confirm`-mode graph pause waits before expiring |
| `SESSION_INACTIVITY_MINUTES` | `30` | Minutes of inactivity before a session is considered stale |
| `LOG_LEVEL` | `INFO` | Structlog level: `DEBUG` / `INFO` / `WARNING` |
| `LOG_DEV` | `false` | Human-readable structlog console output (`true` = dev, `false` = JSON) |
| `LOG_FILE` | `""` | Tee logs to this file as well as stdout (empty = stdout only) |

### Browser sidecar

| Variable | Default | Description |
|---|---|---|
| `BROWSER_SERVICE_URL` | `http://ze-browser.internal:8080` | URL of the browser sidecar service |
| `BROWSER_TIMEOUT_SECONDS` | `20` | HTTP timeout for browser requests |

### Prospecting

| Variable | Default | Description |
|---|---|---|
| `PROSPECTING_MAX_ITERATIONS` | `15` | Max ReAct loop iterations for the prospecting agent |
| `PROSPECTING_STALE_TIMEOUT_MINUTES` | `10` | Minutes before an in-progress campaign is considered stuck |

### Agent harness

| Variable | Default | Description |
|---|---|---|
| `MAX_TOOL_CALLS_PER_TURN` | `20` | Hard cap on tool calls per graph invocation (enforced by `ToolCallCapHook`) |

---

## `config/config.yaml`

Structural settings only: model aliases, memory graph, contacts consolidation, proactive
crons, and news. Secrets and deployment values stay in `.env`. Persona profiles live in
`config/persona.yaml`. Agent metadata is declared as class attributes on `@agent`
classes — there is no `agents:` block in YAML.

Optional `routing:` overrides (threshold, gap_threshold, fallback_model) use ze-core
defaults when omitted — see `ze_core.routing.types.RouterConfig`.

### `models:`

System-level model assignments for internal flows. These are not agent models.

```yaml
models:
  router:           anthropic/claude-haiku-4-5      # Haiku fallback + fact dedup merge
  synthesis:        anthropic/claude-haiku-4-5      # Multi-agent response synthesis + episode summaries
  profile:          anthropic/claude-haiku-4-5      # User profile facet synthesis
  reminders:        anthropic/claude-haiku-4-5      # Calendar reminder interval assessment
  insights:         anthropic/claude-haiku-4-5      # Weekly insight generation
  whisper:          openai/gpt-audio                # Voice note transcription
  vision_caption:   google/gemini-flash-1.5         # Routing caption for photos with no text
```

`whisper` is used by the preprocessing node to convert voice input to text before
routing. `vision_caption` is called during preprocessing when a photo arrives without
a text caption so the embedding router has text to score. Both are invoked via
OpenRouter.

### `memory:`

```yaml
memory:
  graph:
    enabled: true          # Enable the graph relationship layer
    max_hops: 1            # Expansion hops during retrieval augmentation
    max_relationships: 20  # Max graph neighbours fetched per expansion

  # Optional consolidation overrides — defaults defined in ze_memory/defaults.py
  consolidation:
    merge_silent_threshold: 0.95
    merge_llm_threshold: 0.85
    contradicted_ttl_days: 30
    unreviewed_ttl_days: 90
    expiry_grace_days: 7
    episode_recency_days: 14
    episode_min_archive_batch: 10
    nightly_cron: "0 2 * * *"

  profile:
    min_facts: 3       # Skip profile synthesis below this many reviewed facts
    episode_limit: 50  # Max episodes fed into the synthesis prompt
```

### `contacts:`

```yaml
contacts:
  consolidation:
    episode_batch_size: 10
    max_episodes_per_run: 50
    nightly_cron: "0 3 * * *"
    review_cron: "30 8 * * *"
  follow_up:
    stale_days: 7
    max_nudges: 3
```

### `proactive:`

Controls all proactive push behaviours.

```yaml
proactive:
  briefing:
    enabled: true
    cron: "0 8 * * *"               # When to send the morning briefing (cron, UTC)
    unreviewed_nudge_threshold: 5   # Include a review nudge if unreviewed facts >= this

  alerts:
    workflow_failure_enabled: true
    workflow_failure_cooldown_hours: 1  # Min hours between repeated alerts for the same workflow

  calendar:
    sync_enabled: true
    sync_cron: "45 7 * * *"   # When to sync Google Calendar for reminders (before briefing)
    sync_days_ahead: 7        # How many days ahead to pull events

  insights:
    enabled: true
    cron: "0 7 * * 0"           # When to run insight generation (Sunday 7 AM UTC)
    lookback_days: 7
    min_evidence: 3
    max_per_run: 3
    category_cooldown_days: 7   # Suppress same insight category within this window

  goal_narrative:
    enabled: true
    cron: "0 18 * * 0"

  goal_suggestion:
    enabled: true
    cron: "0 19 * * 0"

  stuck_goals:
    enabled: true
    cron: "0 9 * * 2"

  accountability:
    enabled: true
    schedule: "0 9 * * 1"          # Monday 09:00 — weekly activity narrative
    cost_anomaly_schedule: "0 */6 * * *"  # every 6 h — per-agent cost outlier scan
    anomaly_threshold: 4.0          # multiplier above baseline to trigger an alert
    anomaly_min_samples: 5          # min historical runs needed before alerting
    anomaly_retention_days: 30      # prune anomaly records older than N days
    stall_days: 3                   # milestone idle days before counted as stalled
```

Disable any proactive feature by setting `enabled: false` or toggling the relevant flag.

### `news:`

Controls the `ze-news` plugin. The plugin is loaded when `news.enabled: true` and at
least one source is configured.

```yaml
news:
  enabled: true
  fetch_schedule: "*/30 * * * *"   # Cron for the RSS fetch job
  retention_days: 7                 # Hard-delete articles older than N days
  model: "openai/gpt-4o-mini"      # Model used by the news agent
  briefing_limit: 8                 # Total headlines in the morning briefing

  personalization:
    enabled: true
    explore_ratio: 0.2             # Fraction reserved for off-profile discovery
    candidate_multiplier: 3        # Over-fetch multiplier before filtering
    briefing_limit: 8
    min_facts: 5                   # Min user facts required for interest ranking

  credibility:
    enabled: true
    llm_scoring: true
    model: "openai/gpt-4o-mini"
    flag_in_briefing: true
    briefing_summary: true

  sources:
    - key: bbc_world
      type: rss
      url: "https://feeds.bbci.co.uk/news/world/rss.xml"
      tags: [global, general]
```

**Source tags** are arbitrary strings used by the `get_headlines` tool and the briefing
for filtering. Useful conventions: `global`, `local`, `tech`, `pt`, `hacker-news`.

---

## `config/persona.yaml`

Controls Ze's tone and personality across all agent responses via named profiles and
continuous dials.

```yaml
profile: default   # Active profile name. Overridden at runtime by DB value.
locale: en         # BCP 47 locale for progress message translations (en | pt)

profiles:
  default:
    traits: [direct, warm, concise]
    verbosity: concise        # concise | balanced | detailed
    custom_instructions: ""   # Free-form text appended after traits, before memory context
    dials:
      humor:       0.3        # 0 = none → 1 = freely witty
      directness:  0.9        # 0 = Socratic → 1 = blunt conclusions-first
      formality:   0.2        # 0 = casual → 1 = formal
      depth:       0.5        # 0 = surface → 1 = full elaboration

  stoic:
    traits: [precise, measured]
    verbosity: concise
    custom_instructions: ""
    dials:
      humor: 0.05
      directness: 1.0
      formality: 0.7
      depth: 0.4

  playful:
    traits: [warm, curious, witty]
    verbosity: balanced
    custom_instructions: ""
    dials:
      humor: 0.85
      directness: 0.4
      formality: 0.1
      depth: 0.6
```

**Profiles** are named personality presets. Add as many as you like under `profiles:`.
The `profile:` key sets the YAML default; the active profile is overridden at runtime
by the DB value in `persona_state` (set conversationally) and survives restarts.

**Dials** are continuous `[0.0, 1.0]` values. Each dial maps to a prose clause injected
into the identity block only at the extremes (below `0.2` or above `0.8`). The neutral
band `[0.2, 0.8)` is intentionally silent.

| Dial | Low (< 0.2) effect | High (≥ 0.8) effect |
|---|---|---|
| `humor` | No humor | Openly funny |
| `directness` | Socratic / exploratory | Conclusions first, no preamble |
| `formality` | Casual, first names | Formal and precise |
| `depth` | Surface level | Full elaboration with examples |

**`custom_instructions`** is free-form text appended to every system prompt for that
profile — useful for "Always respond in European Portuguese" or "Use my name João."

Profile switches and dial overrides are persisted in the `persona_state` DB table and
survive restarts. The YAML values serve as defaults when no DB override exists.

---

## Enabling calendar and email

Both require Google OAuth2 credentials.

1. Create a Google Cloud project, enable Calendar and Gmail APIs.
2. Create an OAuth2 client ID (Desktop application type).
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`.
4. Run the one-time auth script locally:
   ```bash
   python scripts/google_auth.py
   ```
   This opens a browser, completes the OAuth flow, and prints the refresh token.
5. Set `GOOGLE_REFRESH_TOKEN` in `.env` (locally) or as a Fly secret (production).

Calendar and email agents are enabled automatically whenever `GOOGLE_REFRESH_TOKEN`
is set — there are no `calendar.enabled` / `email.enabled` YAML flags.

---

## Hot-reloading

Send `SIGHUP` to the running process to reload capability modes and YAML config
without restarting:

```bash
kill -HUP <pid>
# or on Fly.io:
fly ssh console -C "kill -HUP 1"
```

Model assignments and plugin configuration require a full restart.
