import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx
import structlog

from ze.errors import OpenRouterError, RateLimitError
from ze.openrouter.types import TokenUsage

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_BACKOFFS = [1.0, 2.0, 4.0]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        http_client: httpx.AsyncClient,
        logger: structlog.BoundLogger,
        http_referer: str = "https://github.com/ze",
        title: str = "Ze Personal Assistant",
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._http = http_client
        self._log = logger
        self._http_referer = http_referer
        self._title = title

    # ── Public interface ──────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> str:
        """Send a non-streaming completion. Returns the full response string."""
        payload = self._payload(messages, model, system, temperature, max_tokens, stream=False)
        start = time.monotonic()

        response = await self._post_with_retry(payload)
        duration_ms = int((time.monotonic() - start) * 1000)

        data = response.json()
        usage = _extract_usage(data)
        content: str = data["choices"][0]["message"]["content"]

        self._log.info(
            "openrouter_complete",
            model=model,
            duration_ms=duration_ms,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            success=True,
        )
        return content

    async def stream(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Send a streaming completion. Yields decoded token chunks."""
        payload = self._payload(messages, model, system, temperature, max_tokens, stream=True)
        url = f"{self._base_url}/chat/completions"
        start = time.monotonic()
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(_BACKOFFS, start=1):
            async with self._http.stream("POST", url, json=payload, headers=self._headers()) as response:
                if response.status_code in _RETRYABLE_STATUS:
                    await response.aread()
                    wait = max(backoff, _parse_retry_after(response))
                    self._log.warning(
                        "openrouter_stream_retry",
                        status=response.status_code,
                        attempt=attempt,
                        wait_seconds=wait,
                    )
                    last_exc = (
                        RateLimitError("Rate limited", status_code=response.status_code)
                        if response.status_code == 429
                        else OpenRouterError(f"HTTP {response.status_code}", status_code=response.status_code)
                    )
                    await asyncio.sleep(wait)
                    continue

                if response.status_code >= 400:
                    body = await response.aread()
                    raise OpenRouterError(
                        f"HTTP {response.status_code}: {body.decode()}",
                        status_code=response.status_code,
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        self._log.info(
                            "openrouter_stream",
                            model=model,
                            duration_ms=int((time.monotonic() - start) * 1000),
                            success=True,
                        )
                        return
                    try:
                        chunk = json.loads(data)
                        content = chunk["choices"][0]["delta"].get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
                return

        raise last_exc or OpenRouterError("All retry attempts exhausted")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": self._http_referer,
            "X-Title": self._title,
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        messages: list[dict],
        model: str,
        system: str | None,
        temperature: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        full_messages = (
            [{"role": "system", "content": system}] + messages if system else messages
        )
        return {
            "model": model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    async def _post_with_retry(self, payload: dict) -> httpx.Response:
        url = f"{self._base_url}/chat/completions"
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(_BACKOFFS, start=1):
            try:
                response = await self._http.post(url, json=payload, headers=self._headers())
            except httpx.RequestError as exc:
                last_exc = OpenRouterError(f"Request failed: {exc}")
                if attempt == len(_BACKOFFS):
                    break
                await asyncio.sleep(backoff)
                continue

            if response.status_code in _RETRYABLE_STATUS:
                wait = max(backoff, _parse_retry_after(response))
                self._log.warning(
                    "openrouter_retry",
                    status=response.status_code,
                    attempt=attempt,
                    wait_seconds=wait,
                )
                last_exc = (
                    RateLimitError("Rate limited", status_code=response.status_code)
                    if response.status_code == 429
                    else OpenRouterError(f"HTTP {response.status_code}", status_code=response.status_code)
                )
                await asyncio.sleep(wait)
                continue

            if response.status_code >= 400:
                raise OpenRouterError(
                    f"HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code,
                )

            return response

        raise last_exc or OpenRouterError("All retry attempts exhausted")


def _parse_retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers.get("Retry-After", "0"))
    except ValueError:
        return 0.0


def _extract_usage(data: dict) -> TokenUsage:
    usage = data.get("usage", {})
    return TokenUsage(
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )
