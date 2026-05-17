import asyncio
import time
from collections.abc import AsyncIterator

import structlog
from openrouter import OpenRouter
from openrouter import errors as sdk_errors
from openrouter.components.chatresult import ChatResult
from openrouter.components.chatstreamchunk import ChatStreamChunk
from openrouter.types import UNSET, UNSET_SENTINEL
from ze.errors import OpenRouterError, RateLimitError
from ze.openrouter.types import TokenUsage

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_BACKOFFS = [1.0, 2.0, 4.0]


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        logger: structlog.BoundLogger,
        http_referer: str = "https://github.com/ze",
        title: str = "Ze Personal Assistant",
    ) -> None:
        self._log = logger
        self._sdk = OpenRouter(
            api_key=api_key,
            server_url=base_url.rstrip("/"),
            http_referer=http_referer,
            x_open_router_title=title,
            retry_config=None,
        )

    async def aclose(self) -> None:
        await self._sdk.__aexit__(None, None, None)

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
        full_messages = _build_messages(messages, system)
        start = time.monotonic()
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(_BACKOFFS, start=1):
            try:
                response = await self._sdk.chat.send_async(
                    messages=full_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )
            except sdk_errors.OpenRouterError as exc:
                ze_exc = _map_sdk_error(exc)
                if not _is_retryable(ze_exc):
                    raise ze_exc from exc
                wait = max(backoff, _parse_retry_after(exc))
                self._log.warning(
                    "openrouter_retry",
                    status=ze_exc.status_code,
                    attempt=attempt,
                    wait_seconds=wait,
                )
                last_exc = ze_exc
                await asyncio.sleep(wait)
                continue
            except sdk_errors.NoResponseError as exc:
                last_exc = OpenRouterError(f"Request failed: {exc}")
                if attempt == len(_BACKOFFS):
                    break
                await asyncio.sleep(backoff)
                continue

            if not isinstance(response, ChatResult):
                raise OpenRouterError("Unexpected streaming response for non-streaming call")

            duration_ms = int((time.monotonic() - start) * 1000)
            usage = _extract_usage(response)
            content = response.choices[0].message.content
            if content is None or content is UNSET or content is UNSET_SENTINEL:
                content = ""
            elif not isinstance(content, str):
                content = str(content)

            self._log.info(
                "openrouter_complete",
                model=model,
                duration_ms=duration_ms,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                success=True,
            )
            return content

        raise last_exc or OpenRouterError("All retry attempts exhausted")

    async def stream(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
        """Send a streaming completion. Yields decoded token chunks."""
        full_messages = _build_messages(messages, system)
        start = time.monotonic()
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(_BACKOFFS, start=1):
            try:
                event_stream = await self._sdk.chat.send_async(
                    messages=full_messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                )
            except sdk_errors.OpenRouterError as exc:
                ze_exc = _map_sdk_error(exc)
                if not _is_retryable(ze_exc):
                    raise ze_exc from exc
                wait = max(backoff, _parse_retry_after(exc))
                self._log.warning(
                    "openrouter_stream_retry",
                    status=ze_exc.status_code,
                    attempt=attempt,
                    wait_seconds=wait,
                )
                last_exc = ze_exc
                await asyncio.sleep(wait)
                continue
            except sdk_errors.NoResponseError as exc:
                last_exc = OpenRouterError(f"Request failed: {exc}")
                if attempt == len(_BACKOFFS):
                    break
                await asyncio.sleep(backoff)
                continue

            if isinstance(event_stream, ChatResult):
                raise OpenRouterError("Unexpected non-streaming response for streaming call")

            async with event_stream:
                async for chunk in event_stream:
                    content = _chunk_content(chunk)
                    if content:
                        yield content

            self._log.info(
                "openrouter_stream",
                model=model,
                duration_ms=int((time.monotonic() - start) * 1000),
                success=True,
            )
            return

        raise last_exc or OpenRouterError("All retry attempts exhausted")


def _build_messages(messages: list[dict], system: str | None) -> list[dict]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _chunk_content(chunk: ChatStreamChunk) -> str | None:
    if not chunk.choices:
        return None
    delta = chunk.choices[0].delta
    content = delta.content
    if content is UNSET or content is UNSET_SENTINEL or content is None:
        return None
    return content


def _map_sdk_error(exc: sdk_errors.OpenRouterError) -> OpenRouterError:
    if isinstance(exc, sdk_errors.TooManyRequestsResponseError):
        return RateLimitError(exc.message, status_code=exc.status_code)
    return OpenRouterError(exc.message, status_code=exc.status_code)


def _is_retryable(exc: OpenRouterError) -> bool:
    return exc.status_code in _RETRYABLE_STATUS


def _parse_retry_after(exc: sdk_errors.OpenRouterError) -> float:
    try:
        return float(exc.headers.get("Retry-After", "0"))
    except ValueError:
        return 0.0


def _extract_usage(result: ChatResult) -> TokenUsage:
    usage = result.usage
    if usage is None:
        return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    return TokenUsage(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
    )
