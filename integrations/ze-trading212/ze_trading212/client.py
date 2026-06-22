from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from ze_trading212.settings import get_trading212_settings

_LIVE_BASE = "https://live.trading212.com/api/v0"
_DEMO_BASE = "https://demo.trading212.com/api/v0"


@dataclass(frozen=True)
class Trading212Client:
    """Thin async wrapper around the Trading212 REST API v0.

    All methods raise ``httpx.HTTPStatusError`` on 4xx/5xx responses.
    Callers are responsible for error handling and retry logic.
    """

    api_key: str
    base_url: str

    # -- Portfolio ----------------------------------------------------------

    async def get_account_info(self) -> dict[str, Any]:
        return await self._get("/equity/account/info")

    async def get_cash(self) -> dict[str, Any]:
        return await self._get("/equity/account/cash")

    async def get_portfolio(self) -> list[dict[str, Any]]:
        return await self._get("/equity/portfolio")

    # -- Orders -------------------------------------------------------------

    async def get_orders(self) -> list[dict[str, Any]]:
        return await self._get("/equity/orders")

    async def place_limit_order(
        self,
        ticker: str,
        quantity: float,
        limit_price: float,
        time_validity: str = "DAY",
    ) -> dict[str, Any]:
        return await self._post(
            "/equity/orders/limit",
            {
                "ticker": ticker,
                "quantity": quantity,
                "limitPrice": limit_price,
                "timeValidity": time_validity,
            },
        )

    async def place_market_order(
        self,
        ticker: str,
        quantity: float,
    ) -> dict[str, Any]:
        return await self._post(
            "/equity/orders/market",
            {"ticker": ticker, "quantity": quantity},
        )

    async def cancel_order(self, order_id: int) -> None:
        async with self._session() as client:
            r = await client.delete(f"/equity/orders/{order_id}")
            r.raise_for_status()

    # -- History ------------------------------------------------------------

    async def get_order_history(
        self,
        cursor: int | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        return await self._get("/equity/history/orders", params=params)

    async def get_dividend_history(
        self,
        cursor: int | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        if ticker is not None:
            params["ticker"] = ticker
        return await self._get("/equity/history/dividends", params=params)

    async def get_transaction_history(
        self,
        cursor: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        return await self._get("/equity/history/transactions", params=params)

    # -- Instruments --------------------------------------------------------

    async def get_instruments(self) -> list[dict[str, Any]]:
        return await self._get("/equity/metadata/instruments")

    # -- Internal -----------------------------------------------------------

    def _session(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": self.api_key},
            timeout=30.0,
        )

    async def _get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> Any:
        async with self._session() as client:
            r = await client.get(path, params=params)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        async with self._session() as client:
            r = await client.post(path, json=body)
            r.raise_for_status()
            return r.json()

    # -- Factory ------------------------------------------------------------

    @classmethod
    def from_settings(cls, settings=None) -> Trading212Client | None:
        """Return None if the API key is absent — never raise."""
        _ = settings  # ZeIntegration protocol; credentials come from ze-trading212 env.
        ts = get_trading212_settings()
        if not ts.trading212_api_key:
            return None
        return cls(
            api_key=ts.trading212_api_key,
            base_url=_DEMO_BASE if ts.trading212_demo else _LIVE_BASE,
        )
