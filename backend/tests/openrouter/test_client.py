import json
import pytest
import httpx
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from ze.errors import OpenRouterError, RateLimitError
from ze.logging import configure_logging, get_logger
from ze.openrouter.client import OpenRouterClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture
def mock_http():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def client(mock_http):
    return OpenRouterClient(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        http_client=mock_http,
        logger=get_logger("test"),
    )


def ok_response(content: str, usage: dict | None = None) -> httpx.Response:
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }
    return httpx.Response(200, content=json.dumps(body).encode())


def error_response(status: int, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, content=b'{"error":"fail"}', headers=headers or {})


def stream_ctx(lines: list[str], status: int = 200, headers: dict | None = None):
    """Return an async context manager that mimics httpx streaming."""
    @asynccontextmanager
    async def _ctx(*args, **kwargs):
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.headers = httpx.Headers(headers or {})

        async def _aiter_lines():
            for line in lines:
                yield line

        async def _aread():
            return b""

        mock_resp.aiter_lines = _aiter_lines
        mock_resp.aread = _aread
        yield mock_resp

    return _ctx


def sse_line(content: str) -> str:
    return f'data: {json.dumps({"choices": [{"delta": {"content": content}}]})}'


DONE_LINE = "data: [DONE]"


# ── complete() ────────────────────────────────────────────────────────────────

async def test_complete_returns_content(client, mock_http):
    mock_http.post.return_value = ok_response("Paris")
    result = await client.complete([{"role": "user", "content": "Capital of France?"}], model="test-model")
    assert result == "Paris"


async def test_complete_prepends_system_prompt(client, mock_http):
    mock_http.post.return_value = ok_response("ok")
    await client.complete(
        [{"role": "user", "content": "hi"}],
        model="test-model",
        system="You are Ze.",
    )
    payload = mock_http.post.call_args.kwargs["json"]
    assert payload["messages"][0] == {"role": "system", "content": "You are Ze."}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}


async def test_complete_sends_correct_headers(client, mock_http):
    mock_http.post.return_value = ok_response("ok")
    await client.complete([{"role": "user", "content": "hi"}], model="m")
    headers = mock_http.post.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert "HTTP-Referer" in headers
    assert "X-Title" in headers


async def test_complete_raises_on_4xx(client, mock_http):
    mock_http.post.return_value = error_response(400)
    with pytest.raises(OpenRouterError) as exc_info:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 400


async def test_complete_retries_on_429_then_succeeds(client, mock_http):
    mock_http.post.side_effect = [error_response(429), ok_response("ok")]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == "ok"
    assert mock_http.post.call_count == 2
    mock_sleep.assert_awaited_once()


async def test_complete_retries_on_503_then_succeeds(client, mock_http):
    mock_http.post.side_effect = [error_response(503), ok_response("ok")]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == "ok"


async def test_complete_raises_rate_limit_after_all_retries(client, mock_http):
    mock_http.post.return_value = error_response(429)
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RateLimitError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert mock_http.post.call_count == 3


async def test_complete_raises_openrouter_error_after_5xx_retries(client, mock_http):
    mock_http.post.return_value = error_response(502)
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 502


async def test_complete_respects_retry_after_header(client, mock_http):
    mock_http.post.side_effect = [
        error_response(429, headers={"Retry-After": "10"}),
        ok_response("ok"),
    ]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    # backoff[0] = 1s, Retry-After = 10s → should wait max(1, 10) = 10s
    mock_sleep.assert_awaited_once_with(10.0)


async def test_complete_raises_on_network_error_after_retries(client, mock_http):
    mock_http.post.side_effect = httpx.RequestError("connection refused")
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")


# ── stream() ──────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens(client, mock_http):
    lines = [sse_line("Hello"), sse_line(" world"), DONE_LINE]
    mock_http.stream = stream_ctx(lines)

    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["Hello", " world"]


async def test_stream_stops_at_done(client, mock_http):
    lines = [sse_line("A"), DONE_LINE, sse_line("B")]  # B should never be yielded
    mock_http.stream = stream_ctx(lines)

    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["A"]


async def test_stream_skips_non_data_lines(client, mock_http):
    lines = ["", ": keep-alive", sse_line("token"), DONE_LINE]
    mock_http.stream = stream_ctx(lines)

    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["token"]


async def test_stream_skips_empty_delta_content(client, mock_http):
    no_content_line = f'data: {json.dumps({"choices": [{"delta": {}}]})}'
    lines = [no_content_line, sse_line("real"), DONE_LINE]
    mock_http.stream = stream_ctx(lines)

    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["real"]


async def test_stream_retries_on_429(client, mock_http):
    retry_ctx = stream_ctx([], status=429)
    ok_ctx = stream_ctx([sse_line("ok"), DONE_LINE])

    call_count = 0

    @asynccontextmanager
    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        ctx = retry_ctx if call_count == 1 else ok_ctx
        async with ctx() as r:
            yield r

    mock_http.stream = side_effect
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["ok"]
    assert call_count == 2


async def test_stream_raises_on_4xx(client, mock_http):
    mock_http.stream = stream_ctx([], status=403)
    with pytest.raises(OpenRouterError) as exc_info:
        async for _ in client.stream([{"role": "user", "content": "hi"}], model="m"):
            pass
    assert exc_info.value.status_code == 403
