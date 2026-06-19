from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_trading212.client import Trading212Client, _DEMO_BASE, _LIVE_BASE


def test_from_settings_returns_none_when_unconfigured() -> None:
    settings = MagicMock(spec=[])
    assert Trading212Client.from_settings(settings) is None


def test_from_settings_live_by_default() -> None:
    settings = MagicMock(trading212_api_key="key123", trading212_demo=False)
    client = Trading212Client.from_settings(settings)
    assert client is not None
    assert client.base_url == _LIVE_BASE
    assert client.api_key == "key123"


def test_from_settings_demo_mode() -> None:
    settings = MagicMock(trading212_api_key="key123", trading212_demo=True)
    client = Trading212Client.from_settings(settings)
    assert client is not None
    assert client.base_url == _DEMO_BASE


@pytest.mark.asyncio
async def test_get_portfolio_calls_correct_path() -> None:
    client = Trading212Client(api_key="key", base_url=_LIVE_BASE)
    mock_response = MagicMock()
    mock_response.json.return_value = []
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("ze_trading212.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.get_portfolio()

    mock_http.get.assert_called_once_with("/equity/portfolio", params=None)
    assert result == []


@pytest.mark.asyncio
async def test_get_cash_calls_correct_path() -> None:
    client = Trading212Client(api_key="key", base_url=_LIVE_BASE)
    mock_response = MagicMock()
    mock_response.json.return_value = {"blocked": 0, "free": 1000, "invested": 5000, "total": 6000}
    mock_response.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch("ze_trading212.client.httpx.AsyncClient", return_value=mock_http):
        result = await client.get_cash()

    mock_http.get.assert_called_once_with("/equity/account/cash", params=None)
    assert result["free"] == 1000
