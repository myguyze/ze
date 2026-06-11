"""Tests for OpenRouterClient — SDK calls are mocked via MagicMock."""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openrouter.components.chatassistantmessage import ChatAssistantMessage
from openrouter.components.chatcontenttext import ChatContentText
from openrouter.components.chatchoice import ChatChoice
from openrouter.components.chatresult import ChatResult
from openrouter.components.chatstreamchunk import ChatStreamChunk
from openrouter.components.chatstreamchoice import ChatStreamChoice
from openrouter.components.chatstreamdelta import ChatStreamDelta
from openrouter.components.chattoolcall import ChatToolCall, ChatToolCallFunction
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

from ze_agents.errors import OpenRouterError, RateLimitError
from ze_core.openrouter.client import OpenRouterClient, _build_messages


# ── _build_messages ───────────────────────────────────────────────────────────

class TestBuildMessages:
    def test_no_system_returns_messages_unchanged(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert _build_messages(msgs, None) == msgs

    def test_system_prepended(self):
        msgs = [{"role": "user", "content": "hi"}]
        result = _build_messages(msgs, "You are helpful.")
        assert result[0] == {"role": "system", "content": "You are helpful."}
        assert result[1] == msgs[0]

    def test_empty_system_not_prepended(self):
        msgs = [{"role": "user", "content": "hi"}]
        assert _build_messages(msgs, "") == msgs


# ── Helpers ───────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.chat.send_async = AsyncMock()
    return sdk


@pytest.fixture
def client(mock_sdk):
    with patch("ze_core.openrouter.client.OpenRouter", return_value=mock_sdk):
        yield OpenRouterClient(api_key="test-key", base_url="https://openrouter.ai/api/v1")


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
    data = TooManyRequestsResponseErrorData(error=ErrorBody(code=429, message="rate limited"))
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
    result = await client.complete([{"role": "user", "content": "Capital of France?"}], model="m")
    assert result == "Paris"


async def test_complete_extracts_text_from_content_blocks(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = ChatResult(
        choices=[
            ChatChoice(
                finish_reason="stop",
                index=0,
                message=ChatAssistantMessage(
                    role="assistant",
                    content=[ChatContentText(type="text", text='{"ok": true}')],
                ),
            )
        ],
        created=0,
        id="gen-test",
        model="test-model",
        object="chat.completion",
        system_fingerprint=None,
        usage=ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == '{"ok": true}'


async def test_complete_falls_back_to_reasoning_when_content_empty(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = ChatResult(
        choices=[
            ChatChoice(
                finish_reason="stop",
                index=0,
                message=ChatAssistantMessage(
                    role="assistant",
                    content="",
                    reasoning='{"ok": true}',
                ),
            )
        ],
        created=0,
        id="gen-test",
        model="test-model",
        object="chat.completion",
        system_fingerprint=None,
        usage=ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )
    result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == '{"ok": true}'


async def test_complete_prepends_system_prompt(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = make_result("ok")
    await client.complete([{"role": "user", "content": "hi"}], model="m", system="You are Ze.")
    messages = mock_sdk.chat.send_async.call_args.kwargs["messages"]
    assert messages[0] == {"role": "system", "content": "You are Ze."}
    assert messages[1] == {"role": "user", "content": "hi"}


async def test_complete_raises_on_4xx(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_403()
    with pytest.raises(OpenRouterError) as exc_info:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 403


async def test_complete_retries_on_429_then_succeeds(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [sdk_429(), make_result("ok")]
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        result = await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert result == "ok"
    assert mock_sdk.chat.send_async.call_count == 2
    mock_sleep.assert_awaited_once()


async def test_complete_raises_rate_limit_after_all_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_429()
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(RateLimitError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert mock_sdk.chat.send_async.call_count == 3


async def test_complete_raises_openrouter_error_after_5xx_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_502()
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError) as exc_info:
            await client.complete([{"role": "user", "content": "hi"}], model="m")
    assert exc_info.value.status_code == 502


async def test_complete_respects_retry_after_header(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [sdk_429(retry_after="10"), make_result("ok")]
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await client.complete([{"role": "user", "content": "hi"}], model="m")
    mock_sleep.assert_awaited_once_with(10.0)


async def test_complete_raises_on_network_error_after_retries(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = NoResponseError("connection refused")
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(OpenRouterError):
            await client.complete([{"role": "user", "content": "hi"}], model="m")


# ── stream() ──────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = FakeEventStream([make_chunk("Hello"), make_chunk(" world")])
    tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["Hello", " world"]


async def test_stream_retries_on_429(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = [sdk_429(), FakeEventStream([make_chunk("ok")])]
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        tokens = [chunk async for chunk in client.stream([{"role": "user", "content": "hi"}], model="m")]
    assert tokens == ["ok"]
    assert mock_sdk.chat.send_async.call_count == 2


async def test_stream_raises_on_4xx(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_403()
    with pytest.raises(OpenRouterError) as exc_info:
        async for _ in client.stream([{"role": "user", "content": "hi"}], model="m"):
            pass
    assert exc_info.value.status_code == 403


# ── complete_with_tools() ─────────────────────────────────────────────────────

def make_tool_result(
    content: str | None,
    tool_calls: list[ChatToolCall] | None = None,
    usage: ChatUsage | None = None,
) -> ChatResult:
    return ChatResult(
        choices=[
            ChatChoice(
                finish_reason="tool_calls" if tool_calls else "stop",
                index=0,
                message=ChatAssistantMessage(
                    role="assistant",
                    content=content,
                    tool_calls=tool_calls,
                ),
            )
        ],
        created=0,
        id="gen-tool",
        model="test-model",
        object="chat.completion",
        system_fingerprint=None,
        usage=usage or ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def make_tool_call(name: str, args: str, call_id: str = "c1") -> ChatToolCall:
    return ChatToolCall(
        id=call_id,
        type="function",
        function=ChatToolCallFunction(name=name, arguments=args),
    )


_TOOLS = [{"type": "function", "function": {"name": "web_search", "description": "search", "parameters": {}}}]


async def test_complete_with_tools_returns_text_when_no_tool_calls(client, mock_sdk):
    mock_sdk.chat.send_async.return_value = make_tool_result("Answer.")
    text, calls = await client.complete_with_tools(
        [{"role": "user", "content": "hi"}], model="m", tools=_TOOLS
    )
    assert text == "Answer."
    assert calls is None


async def test_complete_with_tools_returns_tool_call_list(client, mock_sdk):
    tc = make_tool_call("web_search", '{"query": "AI news"}')
    mock_sdk.chat.send_async.return_value = make_tool_result(None, tool_calls=[tc])
    text, calls = await client.complete_with_tools(
        [{"role": "user", "content": "hi"}], model="m", tools=_TOOLS
    )
    assert text is None
    assert calls is not None
    assert len(calls) == 1
    assert calls[0]["name"] == "web_search"
    assert calls[0]["arguments"] == {"query": "AI news"}
    assert calls[0]["id"] == "c1"


async def test_complete_with_tools_parses_invalid_json_args_as_empty(client, mock_sdk):
    tc = make_tool_call("web_search", "not-valid-json")
    mock_sdk.chat.send_async.return_value = make_tool_result(None, tool_calls=[tc])
    _, calls = await client.complete_with_tools(
        [{"role": "user", "content": "hi"}], model="m", tools=_TOOLS
    )
    assert calls[0]["arguments"] == {}


async def test_complete_with_tools_retries_on_429(client, mock_sdk):
    good = make_tool_result("ok")
    mock_sdk.chat.send_async.side_effect = [sdk_429(), good]
    with patch("ze_core.openrouter.client.asyncio.sleep", new_callable=AsyncMock):
        text, _ = await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], model="m", tools=_TOOLS
        )
    assert text == "ok"
    assert mock_sdk.chat.send_async.call_count == 2


async def test_complete_with_tools_raises_on_403(client, mock_sdk):
    mock_sdk.chat.send_async.side_effect = sdk_403()
    with pytest.raises(OpenRouterError) as exc_info:
        await client.complete_with_tools(
            [{"role": "user", "content": "hi"}], model="m", tools=_TOOLS
        )
    assert exc_info.value.status_code == 403
