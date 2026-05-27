from __future__ import annotations

import json
from typing import Any, AsyncIterator

from ze_core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"


def _build_messages(messages: list[dict], system: str | None) -> list[dict]:
    if system:
        return [{"role": "system", "content": system}, *messages]
    return messages


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = _BASE_URL,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._session: Any = None

    async def _get_session(self) -> Any:
        if self._session is None:
            try:
                import aiohttp  # type: ignore[import]
            except ImportError as exc:
                raise ImportError(
                    "aiohttp is required by OpenRouterClient."
                    " Install it with: pip install aiohttp"
                ) from exc
            self._session = aiohttp.ClientSession(
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                }
            )
        return self._session

    async def complete(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        **kwargs: Any,
    ) -> str:
        session = await self._get_session()
        payload: dict[str, Any] = {
            "model": model,
            "messages": _build_messages(messages, system),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(kwargs)
        async with session.post(
            f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def complete_with_tools(
        self,
        messages: list[dict],
        model: str,
        tools: list[dict],
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> tuple[str | None, list[dict] | None]:
        """Send a completion with tool schemas.

        Returns (text, None) when the model produces a text response, or
        (None, tool_call_list) when the model requests tool calls.
        Each item in tool_call_list: {"id": str, "name": str, "arguments": dict}.
        """
        session = await self._get_session()
        payload: dict[str, Any] = {
            "model": model,
            "messages": _build_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "tools": [{"type": "function", "function": t} for t in tools],
        }
        async with session.post(
            f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

        message = data["choices"][0]["message"]
        tool_calls_raw = message.get("tool_calls")

        if tool_calls_raw:
            result = []
            for tc in tool_calls_raw:
                try:
                    args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, ValueError):
                    args = {}
                result.append({
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": args,
                })
            return None, result

        return message.get("content") or "", None

    async def stream(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        session = await self._get_session()
        payload: dict[str, Any] = {
            "model": model,
            "messages": _build_messages(messages, system),
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        async with session.post(
            f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            async for line in resp.content:
                text = line.decode().strip()
                if text.startswith("data: ") and text != "data: [DONE]":
                    try:
                        chunk = json.loads(text[6:])
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        pass

    async def complete_with_usage(
        self,
        messages: list[dict],
        model: str,
        system: str | None = None,
        temperature: float = 0.3,
        max_tokens: int | None = None,
        response_format: dict | None = None,
        **kwargs: Any,
    ) -> tuple[str, dict]:
        """Like complete(), but also returns usage metadata.

        Returns (text, usage) where usage has keys:
          prompt_tokens, completion_tokens, total_tokens, generation_id, duration_ms.
        """
        import time

        session = await self._get_session()
        payload: dict[str, Any] = {
            "model": model,
            "messages": _build_messages(messages, system),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        payload.update(kwargs)

        t0 = time.monotonic()
        async with session.post(
            f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
        duration_ms = int((time.monotonic() - t0) * 1000)

        text = data["choices"][0]["message"]["content"]
        usage_raw = data.get("usage") or {}
        usage = {
            "prompt_tokens": usage_raw.get("prompt_tokens", 0),
            "completion_tokens": usage_raw.get("completion_tokens", 0),
            "total_tokens": usage_raw.get("total_tokens", 0),
            "generation_id": data.get("id"),
            "duration_ms": duration_ms,
        }
        return text, usage

    async def fetch_generation_cost(self, generation_id: str) -> float | None:
        """Fetch the actual USD cost of a generation from OpenRouter.

        Returns None if the cost is unavailable or the request fails.
        """
        session = await self._get_session()
        try:
            async with session.get(
                f"{self._base_url}/generation",
                params={"id": generation_id},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("data", {}).get("total_cost")
        except Exception as exc:
            log.warning("fetch_generation_cost_failed", generation_id=generation_id, error=str(exc))
            return None

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            log.info("openrouter_client_closed")
