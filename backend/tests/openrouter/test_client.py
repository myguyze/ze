import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openrouter.components.chatassistantmessage import ChatAssistantMessage
from openrouter.components.chatchoice import ChatChoice
from openrouter.components.chatresult import ChatResult
from openrouter.components.chatstreamchunk import ChatStreamChunk
from openrouter.components.chatstreamchoice import ChatStreamChoice
from openrouter.components.chatstreamdelta import ChatStreamDelta
from openrouter.components.chatusage import ChatUsage
from openrouter.components.toomanyrequestsresponseerrordata import (
    TooManyRequestsResponseErrorData as ErrorBody,
)
from openrouter.errors import (
    BadGatewayResponseError,
    ForbiddenResponseError,
    NoResponseError,
    TooManyRequestsResponseError,
    TooManyRequestsResponseErrorData,
)

from ze.errors import OpenRouterError, RateLimitError
from ze.logging import configure_logging, get_logger
from ze.openrouter.client import OpenRouterClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.chat.send_async = AsyncMock()
    return sdk


@pytest.fixture
def client(mock_sdk):
    with patch("ze.openrouter.client.OpenRouter", return_value=mock_sdk):
        yield OpenRouterClient(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            logger=get_logger("test"),
            http_referer="https://github.com/ze",
            title="Ze Personal Assistant",
        )


def make_result(content: str, usage: ChatUsage | None = None) -> ChatResult:
    return ChatResult(
        choices=[
            ChatChoice(
                finish_reason="stop",
                index=0,
                message=ChatAssistantMessage(role="assistant", content=content),
            )
        ],
        created=0,
        id="gen-test",
        model="test-model",
        object="chat.completion",
        system_fingerprint=None,
        usage=usage or ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def make_chunk(content: str | None) -> ChatStreamChunk:
    delta = ChatStreamDelta(content=content) if content is not None else ChatStreamDelta()
    return ChatStreamChunk(
        choices=[ChatStreamChoice(delta=delta, finish_reason=None, index=0)],
        created=0,
        id="chunk-test",
        model="test-model",
        object="chat.completion.chunk",
    )


class FakeEventStream:
    def __init__(self, chunks: list[ChatStreamChunk]) -> None:
        self._chunks = chunks
        self.response = MagicMock()

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


def sdk_429(retry_after: str | None = None) -> TooManyRequestsResponseError:
    headers = {"Retry-After": retry_after} if retry_after else {}
    response = httpx.Response(
        429,
        headers=headers,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    data = TooManyRequestsResponseErrorData(
        error=ErrorBody(code=429, message="rate limited"),
    )
    return TooManyRequestsResponseError(data=data, raw_response=response)


def sdk_502() -> BadGatewayResponseError:
    from openrouter.components.badgatewayresponseerrordata import (
        BadGatewayResponseErrorData as GatewayBody,
    )
    from openrouter.errors import BadGatewayResponseErrorData

    response = httpx.Response(
        502,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    data = BadGatewayResponseErrorData(error=GatewayBody(code=502, message="bad gateway"))
    return BadGatewayResponseError(data=data, raw_response=response)


def sdk_403() -> ForbiddenResponseError:
    from openrouter.components.forbiddenresponseerrordata import (
        ForbiddenResponseErrorData as ForbiddenBody,
    )
    from openrouter.errors import ForbiddenResponseErrorData

    response = httpx.Response(
        403,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    data = ForbiddenResponseErrorData(error=ForbiddenBody(code=403, message="forbidden"))
    return ForbiddenResponseError(data=data, raw_response=response)


# ── complete() ────────────────────────────────────────────────────────────────

async def test_complete_returns_content(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = make_result("Paris")
    result = await client.complete(
        [{"role": "user", "content": "Capital of France?"}],
        model="test-model",
    )
    assert result == "Paris"


async def test_complete_prepends_system_prompt(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = make_result("ok")
    await client.complete(
        [{"role": "user", "content": "hi"}],
        model="test-model",
        system="You are Ze.",
    )
    messages = mock_sdk.chat.send_async.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "You are Ze."}
    assert messages[1] == {"role": "user", "content": "hi"}


async def test_complete_configures_sdk_attribution(client):
    with patch("ze.openrouter.client.OpenRouter") as mock_cls:
        OpenRouterClient(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            logger=get_logger("test"),
            http_referer="https://github.com/ze",
            title="Ze Personal Assistant",
        )
    mock_cls.assert_called_once_with(
        api_key="test-key",
        server_url="https://openrouter.ai/api/v1",
        http_referer="https://github.com/ze",
        x_open_router_title="Ze Personal Assistant",
        retry_config=None,
    )


async def test_complete_raises_on_4xx(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_403()
    with pytest.raises(OpenRouterError) as exc_info:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 403


async def test_complete_retries_on_429_then_succeeds(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [sdk_429(), make_result("ok")]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == "ok"
    assert mock_sdk.chat.send_async.call_count == 2
    mock_sleep.assert_awaited_once()


async def test_complete_retries_on_503_then_succeeds(client, mock_sdk):
    from openrouter.components.serviceunavailableresponseerrordata import (
        ServiceUnavailableResponseErrorData as UnavailableBody,
    )
    from openrouter.errors import (
        ServiceUnavailableResponseError,
        ServiceUnavailableResponseErrorData,
    )

    response = httpx.Response(
        503,
        request=httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions"),
    )
    err = ServiceUnavailableResponseError(
        data=ServiceUnavailableResponseErrorData(
            error=UnavailableBody(code=503, message="unavailable"),
        ),
        raw_response=response,
    )
    mock_sdk.chat.send_async.side_effect = [err, make_result("ok")]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == "ok"


async def test_complete_raises_rate_limit_after_all_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_429()
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RateLimitError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert mock_sdk.chat.send_async.call_count == 3


async def test_complete_raises_openrouter_error_after_5xx_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_502()
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 502


async def test_complete_respects_retry_after_header(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [sdk_429(retry_after="10"), make_result("ok")]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    mock_sleep.assert_awaited_once_with(10.0)


async def test_complete_raises_on_network_error_after_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = NoResponseError("connection refused")
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")


# ── stream() ──────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = FakeEventStream(
        [make_chunk("Hello"), make_chunk(" world")]
    )
    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["Hello", " world"]


async def test_stream_stops_at_end_of_stream(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = FakeEventStream(
        [make_chunk("A"), make_chunk("B")]
    )
    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["A", "B"]


async def test_stream_skips_empty_delta_content(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = FakeEventStream(
        [ChatStreamChunk(
            choices=[ChatStreamChoice(delta=ChatStreamDelta(), finish_reason=None, index=0)],
            created=0,
            id="chunk-test",
            model="test-model",
            object="chat.completion.chunk",
        ), make_chunk("real")]
    )
    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["real"]


async def test_stream_retries_on_429(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [
        sdk_429(),
        FakeEventStream([make_chunk("ok")]),
    ]
    with patch("ze.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["ok"]
    assert mock_sdk.chat.send_async.call_count == 2


async def test_stream_raises_on_4xx(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_403()
    with pytest.raises(OpenRouterError) as exc_info:
        async for _ in client.stream([{"role": "user", "content": "hi"}], model="m"):
            pass
    assert exc_info.value.status_code == 403
