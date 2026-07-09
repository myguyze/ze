# OpenRouter Client — Spec

## Purpose

Isolated async HTTP client for all OpenRouter API calls made by Ze. Handles
streaming, retries with `Retry-After` respect, per-agent model config, and error
normalisation into Ze's error hierarchy. Every LLM call in the system goes through
this client — no module calls OpenRouter directly.

## Responsibilities

- Send chat completion requests to OpenRouter via HTTPS.
- Support non-streaming completions via `complete()` — returns `str`.
- Support streaming completions via `stream()` — returns `AsyncIterator[str]`.
- Retry on `429` (rate limit) and `5xx` (server error) with exponential backoff,
  respecting the `Retry-After` response header.
- Normalise all OpenRouter HTTP errors into `OpenRouterError` (from `ze/errors.py`).
- Accept per-call model override.
- Log every call with model, agent, latency, token usage, and success/failure.

## Out of Scope

- Does not choose which model to use — callers pass the model string.
- Does not manage agent state or memory.
- Does not stream tokens to the WebSocket — it yields chunks to the caller.
- Does not implement tool use / function calling (not needed for Phase 1–2).

## Interface Contract

```python
class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        http_client: httpx.AsyncClient,
        logger: structlog.BoundLogger,
    ) -> None: ...

    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> str:
        """Send a non-streaming completion. Returns the full response string."""
        ...

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str,
        model: str,
        duration_seconds: float | None = None,
    ) -> str:
        """Transcribe audio via an OpenRouter Whisper-compatible model.

        Unsupported formats are converted to mp3 via ffmpeg. Returns the stripped
        transcript. Sets telemetry context (flow=transcription, agent=whisper) before
        calling complete() so cost rows are attributed correctly.
        """
        ...

    async def stream(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Send a streaming completion. Yields decoded token chunks."""
        ...
```

### `messages` format

Standard OpenAI-compatible chat format:

```python
[
    {"role": "user",      "content": "What is the capital of France?"},
    {"role": "assistant", "content": "Paris."},
    {"role": "user",      "content": "And Germany?"},
]
```

If `system` is provided, it is prepended as `{"role": "system", "content": system}`
before sending. It is never included in the `messages` list by the caller.

### Outputs / Errors

| Condition | Behaviour |
|-----------|-----------|
| HTTP 200, non-streaming | Return `choices[0].message.content` as `str` |
| HTTP 200, streaming | Yield decoded content chunks; stop on `[DONE]` sentinel |
| HTTP 429 | Retry with backoff (see below). After 3 attempts: raise `RateLimitError` |
| HTTP 5xx | Retry with backoff. After 3 attempts: raise `OpenRouterError` |
| HTTP 4xx (not 429) | Raise `OpenRouterError` immediately, no retry |
| JSON decode failure | Raise `OpenRouterError` with raw response body in message |
| Network timeout | Raise `OpenRouterError` with timeout details |

## Data Structures

`ze/openrouter/types.py`

```python
from dataclasses import dataclass

@dataclass
class CompletionRequest:
    model: str
    messages: list[dict]
    system: str | None
    temperature: float
    max_tokens: int
    stream: bool

@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
```

`TokenUsage` is extracted from the final response and included in the log record.
It is not returned to callers in Phase 1 but is logged for future cost tracking.

## Retry Logic

```
Attempt 1 → fail (429 or 5xx)
    read Retry-After header → retry_after (default 0 if absent)
    backoff = 1s
    wait max(backoff, retry_after)

Attempt 2 → fail
    backoff = 2s
    wait max(backoff, retry_after)

Attempt 3 → fail
    backoff = 4s
    wait max(backoff, retry_after)

Attempt 4 → raise RateLimitError or OpenRouterError
```

- `Retry-After` header value is parsed as integer seconds.
- Jitter is not added in Phase 1 (single-user system, no thundering herd).
- `5xx` retries apply to: 500, 502, 503, 504.
- `4xx` other than 429 are not retried.

## Configuration

Read from `ze/settings.py` (loaded from `.env`):

```python
OPENROUTER_API_KEY: str
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
OPENROUTER_HTTP_REFERER: str = "https://github.com/ze"   # required by OpenRouter
OPENROUTER_TITLE: str = "Ze Personal Assistant"          # X-Title header
```

Model strings per agent are read from `config/models.yaml`:

```yaml
models:
  router:    anthropic/claude-haiku-4-5
  calendar:  anthropic/claude-haiku-4-5
  email:     anthropic/claude-haiku-4-5
  research:  anthropic/claude-sonnet-4-5
  workflow:  anthropic/claude-sonnet-4-5
  companion: anthropic/claude-sonnet-4-5
  synthesis: anthropic/claude-haiku-4-5
```

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `httpx` | Async HTTP client with HTTP/2 support |
| `ze.errors` | `OpenRouterError`, `RateLimitError` |
| `ze.logging` | Structured call log with latency + token usage |

## Implementation Notes

- Use `httpx.AsyncClient` with `http2=True`. HTTP/2 multiplexing reduces latency
  on concurrent requests (e.g. compound task fan-out).
- The `httpx.AsyncClient` instance is passed in via constructor — do not create it
  inside the client class. This allows the caller to manage the client lifecycle
  and inject a mock in tests.
- Set required headers on every request:

```python
headers = {
    "Authorization": f"Bearer {self.api_key}",
    "HTTP-Referer": self.settings.openrouter_http_referer,
    "X-Title": self.settings.openrouter_title,
    "Content-Type": "application/json",
}
```

- Streaming implementation: use `httpx` SSE response iteration. Yield each decoded
  content chunk. Skip chunks where `choices[0].delta.content` is `None`. Stop when
  the line is `data: [DONE]`.

```python
async def stream(self, ...) -> AsyncIterator[str]:
    async with self.http_client.stream("POST", url, json=payload, headers=headers) as r:
        async for line in r.aiter_lines():
            if line.startswith("data: "):
                data = line[6:]
                if data == "[DONE]":
                    return
                chunk = json.loads(data)
                content = chunk["choices"][0]["delta"].get("content")
                if content:
                    yield content
```

- Log record shape (emitted after every call):

```python
{
    "event":             "openrouter_call",
    "model":             model,
    "agent":             agent,           # bound to logger by caller
    "session_id":        session_id,      # bound to logger by caller
    "duration_ms":       int,
    "prompt_tokens":     int,
    "completion_tokens": int,
    "success":           bool,
    "error":             str | None,
}
```

- The `agent` and `session_id` fields are not passed to `complete()`/`stream()`.
  They are bound to the logger at the API layer via structlog context vars before
  the call is made.

## Open Questions

All resolved.
