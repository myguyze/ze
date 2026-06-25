# Ze — Browser Sidecar

Ze uses a separate **browser sidecar** for headless page extraction. Chromium runs in
its own container/process; the main API talks to it over HTTP. This keeps the backend
image small and cold starts fast.

| Piece | Location | Role |
|---|---|---|
| Sidecar service | `sidecar/browser/` | Playwright + FastAPI — `GET /health`, `POST /extract` |
| Python client | `core/ze-browser/` | `BrowserClient` — injected into `ze-api`'s container |
| Prospecting agent | `plugins/ze-prospecting/` | Primary consumer — `browser_extract` tool |
| Ingestion | `core/ze-ingestion/` | `BrowserFetcher` for JS-heavy pages |

If the sidecar is unreachable, Ze logs a warning at startup and prospecting falls back
to web-search-only research. Individual `browser_extract` calls return an error string
the agent can skip.

See [configuration.md](configuration.md#browser-sidecar) for env vars.

---

## Local development

### Docker Compose (full stack)

`docker-compose.yml` includes a `browser` service. `make docker-up` starts Postgres,
the sidecar, and the backend together. The backend gets
`BROWSER_SERVICE_URL=http://browser:8080` from compose overrides.

```bash
make docker-up
python scripts/check_browser_health.py --probe
```

The compose healthcheck uses fast `GET /health` only (milliseconds). Use the probe
after startup when you need to confirm Playwright can actually fetch a page.

### Hybrid workflow (`make dev` on the host)

Most day-to-day dev uses Postgres from compose and uvicorn on the host:

```bash
make db-up
docker compose up -d browser    # sidecar only
```

Set in `apps/ze-api/.env`:

```
BROWSER_SERVICE_URL=http://localhost:8080
```

Then `make dev` as usual.

### Sidecar only

Build and run from `sidecar/browser/` — see
[sidecar/browser/README.md](../sidecar/browser/README.md) for API details and a
non-Docker setup.

---

## Health checks

`scripts/check_browser_health.py` is the repo-standard way to verify the sidecar from
your machine (or CI):

```bash
# Fast — process is listening
python scripts/check_browser_health.py
python scripts/check_browser_health.py http://localhost:8080

# Smoke test — launches Chromium, POST /extract on example.com (~10–45 s)
python scripts/check_browser_health.py --probe
python scripts/check_browser_health.py --probe --probe-timeout 60
```

| Check | What it proves | Use when |
|---|---|---|
| Default (`GET /health`) | FastAPI is up | After compose up, quick ping |
| `--probe` (`POST /extract`) | Chromium + network + extraction work | Debugging prospecting failures, post-deploy smoke |

Do **not** use `--probe` in Docker Compose healthchecks — it is slow and needs outbound
network. Compose keeps the inline `/health` check so `backend` starts promptly.

---

## Production (Fly.io)

The sidecar deploys as a **separate Fly app** (`sidecar/browser/fly.toml`), not inside
the main `ze-api` image. Ze reaches it at `http://ze-browser.internal:8080` on Fly's
private network. Deploy both apps to the **same region**.

```bash
cd sidecar/browser
fly deploy
```

The main backend deploy does not redeploy the sidecar — release them independently.
Full Fly setup: [sidecar/browser/README.md](../sidecar/browser/README.md).

From a Fly machine you can smoke-test with:

```bash
python scripts/check_browser_health.py http://ze-browser.internal:8080 --probe
```

---

## Further reading

- [sidecar/browser/README.md](../sidecar/browser/README.md) — API contract, extractor behaviour, Fly config
- [core/ze-browser/README.md](../core/ze-browser/README.md) — `BrowserClient` package
- [specs/phases/26-prospecting-agent.md](../specs/phases/26-prospecting-agent.md) — original design
- [deployment.md](deployment.md) — main backend Fly deploy
