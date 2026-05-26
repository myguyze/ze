from __future__ import annotations

from typing import Any, AsyncIterator

from ze_core.logging import get_logger

log = get_logger(__name__)

_BASE_URL = "https://openrouter.ai/api/v1"


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
        max_tokens: int | None = None,
    ) -> str:
        session = await self._get_session()
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        async with session.post(
            f"{self._base_url}/chat/completions", json=payload
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[dict],
        model: str,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        session = await self._get_session()
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
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
                    import json
                    try:
                        chunk = json.loads(text[6:])
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError):
                        pass

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
            log.info("openrouter_client_closed")
