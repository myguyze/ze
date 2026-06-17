# ze-browser

Playwright browser sidecar client for Ze. Provides a lightweight Python client that communicates with a separately running browser sidecar service, used by the prospecting agent for autonomous web research.

## Role in Ze

Some agents need to read web pages that have no API — prospect research, company lookups, outreach target discovery. `ze-browser` is the Python client for a headless Playwright sidecar that fetches and extracts page text on demand.

### Key features

- `BrowserClient` — async HTTP client for the sidecar service
- `browse` `@tool` — registered in the prospecting agent's tool set
- Configurable timeouts, text truncation, and request delay for rate limiting

### Integration

The sidecar runs as a separate Docker service (`sidecar/browser/`). `BrowserClient` is injected into `ProspectingPlugin` via `ze-api`'s container. Only `ze-prospecting` depends on this package today.

## Responsibilities

| Module | What it provides |
|---|---|
| `client.py` | `BrowserClient` — async HTTP client for the sidecar service |
| `tool.py` | `browse` `@tool` — registered in the agent tool registry |
| `types.py` | Request/response types |
| `errors.py` | `BrowserError` and subtypes |

## Dependencies

No Ze package dependencies. Depends only on: `aiohttp`.

## Usage

The sidecar runs as a separate Docker service (`sidecar/browser/`). `BrowserClient` is injected into the prospecting agent via the container in `ze-api`.

```python
from ze_browser import BrowserClient

client = BrowserClient(base_url="http://ze-browser.internal:8080", timeout_seconds=20)
result = await client.fetch("https://example.com")
```

## Configuration

| Setting | Description |
|---|---|
| `BROWSER_SERVICE_URL` | URL of the browser sidecar service |
| `BROWSER_TIMEOUT_SECONDS` | Per-request timeout |
| `BROWSER_MAX_TEXT_CHARS` | Max characters returned per page |
| `BROWSER_DELAY_MS` | Delay between requests (rate limiting) |

## Testing

From the repo root:

```bash
make test-browser
```

See [docs/testing.md](../../docs/testing.md).
