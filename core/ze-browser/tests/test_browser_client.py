from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ze_browser import BrowserClient, BrowserError, BrowserResult


def make_client(base_url: str = "http://ze-browser.internal:8080") -> BrowserClient:
    with patch("ze_browser.client.httpx.AsyncClient"):
        return BrowserClient(base_url=base_url, timeout=20)


def make_httpx_response(status_code: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {
        "url": "https://example.com",
        "title": "Example",
        "text": "Page content here",
        "status_code": status_code,
    }
    resp.text = ""
    return resp


async def test_browser_client_extract_returns_result():
    client = make_client()
    mock_resp = make_httpx_response(200, {
        "url": "https://example.com",
        "title": "Example",
        "text": "Hello world",
        "status_code": 200,
    })

    client._client = AsyncMock()
    client._client.post = AsyncMock(return_value=mock_resp)

    result = await client.extract("https://example.com")

    assert isinstance(result, BrowserResult)
    assert result.url == "https://example.com"
    assert result.title == "Example"
    assert result.text == "Hello world"
    assert result.status_code == 200


async def test_browser_client_timeout_raises_browser_error():
    client = make_client()
    client._client = AsyncMock()
    client._client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with pytest.raises(BrowserError, match="timed out"):
        await client.extract("https://example.com")


async def test_browser_client_403_returns_empty_text_no_exception():
    client = make_client()
    mock_resp = make_httpx_response(200, {
        "url": "https://example.com",
        "title": "Blocked",
        "text": "",
        "status_code": 403,
    })

    client._client = AsyncMock()
    client._client.post = AsyncMock(return_value=mock_resp)

    result = await client.extract("https://example.com")

    assert result.text == ""
    assert result.status_code == 403


async def test_browser_client_5xx_raises_browser_error():
    client = make_client()
    mock_resp = make_httpx_response(502)
    mock_resp.text = "Bad gateway"

    client._client = AsyncMock()
    client._client.post = AsyncMock(return_value=mock_resp)

    with pytest.raises(BrowserError, match="502"):
        await client.extract("https://example.com")


async def test_browser_client_connect_error_raises_browser_error():
    client = make_client()
    client._client = AsyncMock()
    client._client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with pytest.raises(BrowserError, match="Cannot reach"):
        await client.extract("https://example.com")


async def test_health_returns_true_on_200():
    client = make_client()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    client._client = AsyncMock()
    client._client.get = AsyncMock(return_value=mock_resp)

    result = await client.health()

    assert result is True


async def test_health_returns_false_on_exception():
    client = make_client()
    client._client = AsyncMock()
    client._client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    result = await client.health()

    assert result is False


async def test_close_calls_aclose():
    client = make_client()
    client._client = AsyncMock()
    client._client.aclose = AsyncMock()

    await client.close()

    client._client.aclose.assert_awaited_once()
