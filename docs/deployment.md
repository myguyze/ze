# Ze — Deployment Guide

Ze runs on [Fly.io](https://fly.io) as a single-machine app with an attached
Postgres database. GitHub Actions handles CI and automated deploys on push to `main`.

The deployment unit is `apps/ze-api/`. The `fly.toml` and `Dockerfile` both live
there.

---

## Prerequisites

- [flyctl](https://fly.io/docs/hands-on/install-flyctl/) installed and authenticated
- A Fly.io account
- All environment variables from `apps/ze-api/.env.example` ready

---

## First-time setup

### 1. Create the Fly app

```bash
cd apps/ze-api
fly launch --no-deploy
```

Accept the generated `fly.toml` defaults or adjust the app name and region. The
current config targets `lhr` (London). Edit `fly.toml` to change the region.

### 2. Provision Postgres

```bash
fly postgres create --name ze-db --region lhr
fly postgres attach ze-db
```

`attach` sets `DATABASE_URL` automatically as a Fly secret. You still need to
set `DATABASE_URL_SYNC` manually (see step 3).

### 3. Set secrets

Set every required env var as a Fly secret. Secrets are encrypted at rest and
injected as environment variables at runtime.

```bash
fly secrets set \
  OPENROUTER_API_KEY=sk-or-... \
  ZE_API_KEY=your-secret-key \
  DATABASE_URL_SYNC="postgresql+psycopg2://..." \
  NTFY_BASE_URL=https://ntfy.sh \
  NTFY_TOPIC=ze-your-topic \
  NTFY_TOKEN=your-ntfy-token \
  TIMEZONE=Europe/Lisbon
```

For calendar and email (if you have Google credentials):

```bash
fly secrets set \
  GOOGLE_CLIENT_ID=... \
  GOOGLE_CLIENT_SECRET=... \
  GOOGLE_REFRESH_TOKEN=...
```

List current secrets (names only, values hidden):
```bash
fly secrets list
```

### 4. Apply database migrations

```bash
fly ssh console -C "python -m alembic upgrade head"
```

Or use the `DATABASE_URL_SYNC` value locally and run `make migrate` pointed at the
production database. The SSH console approach is simpler for initial setup.

### 5. Deploy

```bash
fly deploy
```

The Dockerfile builds the image, Fly pushes it, and the app starts. Check the
logs immediately after:

```bash
fly logs
```

Look for `ze_startup_complete` to confirm the app is healthy.

---

## Ongoing operations

### Deploy

```bash
fly deploy
```

Or push to `main` — GitHub Actions will deploy automatically.

### View logs

```bash
fly logs              # tail live logs
fly logs --tail       # keep tailing
```

### SSH into the running machine

```bash
fly ssh console
```

### Scale

The default config uses one shared-cpu-1x machine with 1 GB RAM. The embedding
model (`paraphrase-multilingual-MiniLM-L12-v2`) loads into ~450 MB RAM at startup.

```bash
fly scale memory 2048   # upgrade to 2 GB if needed
fly scale count 1       # always 1 — Ze is single-user, no horizontal scaling
```

### Run migrations on production

```bash
fly ssh console -C "cd /app && python -m alembic upgrade head"
```

Or from the repo root:
```bash
make migrate  # runs against DATABASE_URL_SYNC
```

### Hot-reload config (no restart)

```bash
fly ssh console -C "kill -HUP 1"
```

This reloads capability modes and YAML settings without interrupting the process.
Changes to model assignments or plugin configuration require a full `fly deploy`.

### Update a secret

```bash
fly secrets set OPENROUTER_API_KEY=sk-or-new-key
```

Fly restarts the machine automatically after a secret update.

---

## CI/CD (GitHub Actions)

Two workflows live in `.github/workflows/`:

**`ci.yml`** — runs on every push and pull request to `main`:
- `ruff check` (linting)
- `pytest` with fast tests only (embedding model tests excluded)

**`deploy-backend.yml`** — runs on merge to `main` when application code changes
(path filter: `apps/ze-api/**`, `core/ze-core/**`, `core/ze-memory/**`,
`plugins/ze-personal/**`, etc.):
- Runs CI first
- Calls `fly deploy --remote-only` from `apps/ze-api/` using a scoped deploy token

### One-time GitHub setup

1. Create a Fly deploy token (scoped to Ze's app, long-lived):
   ```bash
   fly tokens create deploy -x 999999h
   ```
2. Add it as a GitHub Actions secret named `FLY_API_TOKEN`:
   - Repo → Settings → Secrets and variables → Actions → New repository secret

No other secrets are needed in GitHub — all runtime secrets live in Fly.

---

## Machine spec (`fly.toml`)

```toml
[build]
  dockerfile = "Dockerfile"

[env]
  PORT = "8000"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true    # machine sleeps when idle
  auto_start_machines = true   # wakes on incoming request
  min_machines_running = 0

[[vm]]
  memory = "1gb"
  cpu_kind = "shared"
  cpus = 1
```

`auto_stop_machines = true` means the machine sleeps when there is no traffic.
The cold start (machine wake + model load) takes ~5–10 seconds. If this latency
is unacceptable, set `min_machines_running = 1` to keep the machine always warm
(increases monthly cost).

**Note:** WebSocket connections require the machine to stay awake. If you rely on
a persistent WebSocket from the web app, set `min_machines_running = 1` or use
ntfy push notifications as the fallback when the machine is cold.

---

## Troubleshooting

**`ze_startup_complete` not in logs after deploy**

The app failed during startup. Common causes:

- Missing required env var (check `fly secrets list`)
- Database not reachable (check `DATABASE_URL` and Postgres status)
- Migration not applied (run `fly ssh console -C "python -m alembic upgrade head"`)

**WebSocket disconnects / cannot connect**

- Verify `ZE_API_KEY` secret is set and matches what the app sends as the bearer token.
- Check `fly logs` for `ws_handler_error` events.
- If using `auto_stop_machines = true`, the machine may be cold — the first WebSocket
  connect triggers a wake; subsequent reconnects will be faster.

**Database migrations not applied**

```bash
fly ssh console -C "cd /app && python -m alembic current"
fly ssh console -C "cd /app && python -m alembic upgrade head"
```

**Machine OOM (out of memory)**

The embedding model uses ~450 MB. If other memory pressure exists, upgrade:
```bash
fly scale memory 2048
```

**Google Calendar / Gmail 401 errors**

The refresh token has been revoked. Re-run `scripts/google_auth.py` locally,
get a new refresh token, and update the secret:
```bash
fly secrets set GOOGLE_REFRESH_TOKEN=new-token
```

**ntfy push not delivering**

- Confirm `NTFY_TOPIC` and `NTFY_TOKEN` are set correctly.
- Check `fly logs` for `native_interface_ntfy_failed` events.
- Verify the ntfy server is reachable from the Fly machine (use a public server if
  self-hosting over a private network).
