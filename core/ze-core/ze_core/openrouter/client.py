import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator

import structlog
from openrouter import OpenRouter
from openrouter import errors as sdk_errors
from openrouter.components.chatassistantmessage import ChatAssistantMessage
from openrouter.components.chatresult import ChatResult
from openrouter.components.chatstreamchunk import ChatStreamChunk
from openrouter.types import UNSET, UNSET_SENTINEL
from ze_core.errors import OpenRouterError, RateLimitError
from ze_core.openrouter.types import TokenUsage
from ze_core.logging import get_logger

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_BACKOFFS = [1.0, 2.0, 4.0]
_TRANSCRIBE_FORMATS = {"mp3", "wav", "ogg", "flac", "m4a"}
_TRANSCRIBE_SYSTEM = (
    "You are a transcription engine. Transcribe the audio exactly as spoken. "
    "Output only the transcript — no commentary, no punctuation corrections, no explanations."
)


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        logger: structlog.BoundLogger | None = None,
        http_referer: str = "https://github.com/ze",
        title: str = "Ze Personal Assistant",
        cost_tracker=None,
    ) -> None:
        self._log = logger or get_logger(__name__)
        self._cost_tracker = cost_tracker
        self._sdk = OpenRouter(
            api_key=api_key,
            server_url=base_url.rstrip("/"),
            http_referer=http_referer,
            x_open_router_title=title,
            retry_config=None,
        )

    async def aclose(self) -> None:
        await self._sdk.__aexit__(None, None, None)

    async def fetch_generation_cost(self, generation_id: str) -> float | None:
        try:
            resp = await self._sdk.generations.get_generation_async(id=generation_id)
            return resp.data.total_cost
        except Exception as exc:
            self._log.warning("cost_fetch_failed", generation_id=generation_id, error=str(exc))
            return None

    # ── Public interface ──────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
        *,
        response_format: dict | None = None,
        reasoning: dict | None = None,
        audio_seconds: float | None = None,
    ) -> str:
        full_messages = _build_messages(messages, system)
        start = time.monotonic()
        last_exc: Exception | None = None

        for attempt, backoff in enumerate(_BACKOFFS, start=1):
            try:
                request_kwargs: dict = {
                    "messages": full_messages,
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "stream": False,
                }
                if response_format is not None:
                    request_kwargs["response_format"] = response_format
                if reasoning is not None:
                    request_kwargs["reasoning"] = reasoning
                response = await self._sdk.chat.send_async(**request_kwargs)
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
            content = _extract_message_text(response.choices[0].message)

            self._log.info(
                "openrouter_complete",
                model=model,
                duration_ms=duration_ms,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                success=True,
            )
            if self._cost_tracker is not None:
                self._cost_tracker.record(
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    duration_ms=duration_ms,
                    generation_id=response.id or None,
                    audio_seconds=audio_seconds,
                )
            return content

        raise last_exc or OpenRouterError("All retry attempts exhausted")

    async def complete_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> tuple[str | None, list[dict] | None]:
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
                    tools=tools,
                )
            except sdk_errors.OpenRouterError as exc:
                ze_exc = _map_sdk_error(exc)
                if not _is_retryable(ze_exc):
                    raise ze_exc from exc
                wait = max(backoff, _parse_retry_after(exc))
                self._log.warning(
                    "openrouter_tools_retry",
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
                raise OpenRouterError("Unexpected streaming response for tool-call request")

            duration_ms = int((time.monotonic() - start) * 1000)
            usage = _extract_usage(response)
            message = response.choices[0].message

            self._log.info(
                "openrouter_complete_with_tools",
                model=model,
                duration_ms=duration_ms,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                has_tool_calls=bool(message.tool_calls),
                success=True,
            )
            if self._cost_tracker is not None:
                self._cost_tracker.record(
                    model=model,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    duration_ms=duration_ms,
                    generation_id=response.id or None,
                )

            if message.tool_calls:
                tool_call_list = []
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except (json.JSONDecodeError, ValueError):
                        args = {}
                    tool_call_list.append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": args,
                    })
                return None, tool_call_list

            return _extract_message_text(message), None

        raise last_exc or OpenRouterError("All retry attempts exhausted")

    async def transcribe(
        self,
        audio_bytes: bytes,
        audio_format: str,
        model: str,
        duration_seconds: float | None = None,
    ) -> str:
        """Transcribe audio via an OpenRouter Whisper-compatible model.

        Unsupported formats are converted to mp3 via ffmpeg before sending.
        Returns the stripped transcript string.
        """
        fmt = _normalise_audio_format(audio_format)
        if fmt not in _TRANSCRIBE_FORMATS:
            audio_bytes = await _to_mp3(audio_bytes)
            fmt = "mp3"
        message = {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": base64.b64encode(audio_bytes).decode(),
                        "format": fmt,
                    },
                },
                {"type": "text", "text": "Transcribe the audio."},
            ],
        }
        text = await self.complete(
            messages=[message],
            model=model,
            system=_TRANSCRIBE_SYSTEM,
            audio_seconds=duration_seconds,
        )
        self._log.info(
            "transcription_complete",
            model=model,
            audio_bytes=len(audio_bytes),
            audio_format=fmt,
            duration_seconds=duration_seconds,
        )
        return text.strip()

    async def stream(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 1000,
    ) -> AsyncIterator[str]:
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

            stream_usage = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
            async with event_stream:
                async for chunk in event_stream:
                    if chunk.usage is not None:
                        stream_usage = _extract_stream_usage(chunk)
                    content = _chunk_content(chunk)
                    if content:
                        yield content

            duration_ms = int((time.monotonic() - start) * 1000)
            self._log.info(
                "openrouter_stream",
                model=model,
                duration_ms=duration_ms,
                prompt_tokens=stream_usage.prompt_tokens,
                completion_tokens=stream_usage.completion_tokens,
                success=True,
            )
            if self._cost_tracker is not None and stream_usage.total_tokens > 0:
                self._cost_tracker.record(
                    model=model,
                    prompt_tokens=stream_usage.prompt_tokens,
                    completion_tokens=stream_usage.completion_tokens,
                    total_tokens=stream_usage.total_tokens,
                    duration_ms=duration_ms,
                )
            return

        raise last_exc or OpenRouterError("All retry attempts exhausted")


def _normalise_audio_format(fmt: str) -> str:
    """Extract a bare format string from a MIME type or format hint."""
    fmt = fmt.lower()
    for known in ("ogg", "mp3", "wav", "flac", "m4a"):
        if known in fmt:
            return known
    if "mpeg" in fmt:
        return "mp3"
    if "mp4" in fmt:
        return "m4a"
    return fmt.split("/")[-1].split(";")[0].strip()


async def _to_mp3(audio_bytes: bytes) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-i", "pipe:0", "-f", "mp3", "-q:a", "4", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate(input=audio_bytes)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg conversion failed")
    return stdout


def _build_messages(messages: list[dict], system: str | None) -> list[dict]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


def _chunk_content(chunk: ChatStreamChunk) -> str | None:
    if not chunk.choices:
        return None
    delta = chunk.choices[0].delta
    text = _content_to_str(delta.content)
    if not text.strip():
        reasoning = delta.reasoning
        if reasoning not in (UNSET, UNSET_SENTINEL, None) and isinstance(reasoning, str):
            text = reasoning
    return text or None


def _extract_message_text(message: ChatAssistantMessage) -> str:
    text = _content_to_str(message.content)
    if not text.strip():
        reasoning = message.reasoning
        if reasoning not in (UNSET, UNSET_SENTINEL, None) and isinstance(reasoning, str):
            return reasoning
    return text


def _content_to_str(content: object) -> str:
    if content is None or content is UNSET or content is UNSET_SENTINEL:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(text)
        return "".join(parts)
    return str(content)


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


def _extract_stream_usage(chunk: ChatStreamChunk) -> TokenUsage:
    usage = chunk.usage
    if usage is None:
        return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    return TokenUsage(
        prompt_tokens=usage.prompt_tokens or 0,
        completion_tokens=usage.completion_tokens or 0,
        total_tokens=usage.total_tokens or 0,
    )
