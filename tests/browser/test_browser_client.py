from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from ze.browser.client import BrowserClient
from ze.browser.types import BrowserResult
from ze.errors import BrowserError


def make_client(base_url: str = "http://ze-browser.internal:8080") -> BrowserClient:
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


# ── extract() ─────────────────────────────────────────────────────────────────

async def test_browser_client_extract_returns_result():
    client = make_client()
    mock_resp = make_httpx_response(200, {
        "url": "https://example.com",
        "title": "Example",
        "text": "Hello world",
        "status_code": 200,
    })

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = AsyncMock(return_value=mock_resp)

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.extract("https://example.com")

    assert isinstance(result, BrowserResult)
    assert result.url == "https://example.com"
    assert result.title == "Example"
    assert result.text == "Hello world"
    assert result.status_code == 200


async def test_browser_client_timeout_raises_browser_error():
    client = make_client()

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
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

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = AsyncMock(return_value=mock_resp)

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.extract("https://example.com")

    assert result.text == ""
    assert result.status_code == 403


async def test_browser_client_5xx_raises_browser_error():
    client = make_client()
    mock_resp = make_httpx_response(502)
    mock_resp.text = "Bad gateway"

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = AsyncMock(return_value=mock_resp)

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(BrowserError, match="502"):
            await client.extract("https://example.com")


async def test_browser_client_connect_error_raises_browser_error():
    client = make_client()

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(BrowserError, match="Cannot reach"):
            await client.extract("https://example.com")


# ── health() ──────────────────────────────────────────────────────────────────

async def test_health_returns_true_on_200():
    client = make_client()
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(return_value=mock_resp)

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.health()

    assert result is True


async def test_health_returns_false_on_exception():
    client = make_client()

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

    with patch("ze.browser.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.health()

    assert result is False
