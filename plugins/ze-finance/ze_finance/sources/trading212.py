from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from ze_logging import get_logger
from ze_finance.errors import ZeIntegrationError
from ze_finance.types import (
    Account,
    AccountType,
    Asset,
    AssetClass,
    Position,
    Transaction,
    TransactionType,
)

log = get_logger(__name__)

if TYPE_CHECKING:
    from ze_trading212.client import Trading212Client

_ASSET_CLASS_MAP: dict[str, AssetClass] = {
    "STOCK": AssetClass.EQUITY,
    "ETF": AssetClass.ETF,
    "CRYPTO": AssetClass.CRYPTO,
    "BOND": AssetClass.BOND,
}


class Trading212DataSource:
    """DataSource backed by the Trading212 REST API."""

    source_id = "trading212"

    def __init__(self, client: Trading212Client) -> None:
        self._client = client

    async def fetch_account(self) -> Account:
        try:
            info = await self._client.get_account_info()
            cash = await self._client.get_cash()
        except Exception as exc:
            raise ZeIntegrationError(f"Trading212 account fetch failed: {exc}") from exc

        return Account(
            id=f"trading212:{info.get('id', 'default')}",
            source_id=self.source_id,
            account_type=AccountType.ISA
            if info.get("type") == "ISA"
            else AccountType.BROKERAGE,
            name=info.get("currencyCode", "Trading212"),
            currency=info.get("currencyCode", "GBP"),
            balance=Decimal(str(cash.get("free", 0))),
            updated_at=datetime.now(timezone.utc),
        )

    async def fetch_positions(self) -> list[Position]:
        try:
            raw = await self._client.get_portfolio()
        except Exception as exc:
            raise ZeIntegrationError(
                f"Trading212 portfolio fetch failed: {exc}"
            ) from exc

        account = await self.fetch_account()
        positions: list[Position] = []
        for item in raw:
            ticker = item.get("ticker", "")
            quantity = Decimal(str(item.get("quantity", 0)))
            avg_price = Decimal(str(item.get("averagePrice", 0)))
            current_price = Decimal(str(item.get("currentPrice", 0)))
            pnl = Decimal(str(item.get("ppl", 0)))
            notional = quantity * current_price

            asset = Asset(
                ticker=ticker,
                name=item.get("fullName", ticker),
                asset_class=_ASSET_CLASS_MAP.get(
                    item.get("type", ""), AssetClass.EQUITY
                ),
                currency=account.currency,
            )
            positions.append(
                Position(
                    account_id=account.id,
                    asset=asset,
                    quantity=quantity,
                    notional=notional,
                    average_price=avg_price,
                    current_price=current_price,
                    unrealised_pnl=pnl,
                    currency=account.currency,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        return positions

    async def fetch_transactions(self, since: datetime) -> list[Transaction]:
        try:
            raw_orders = await self._client.get_order_history()
            raw_dividends = await self._client.get_dividend_history()
            raw_cash = await self._client.get_transaction_history()
        except Exception as exc:
            raise ZeIntegrationError(
                f"Trading212 transaction fetch failed: {exc}"
            ) from exc

        account = await self.fetch_account()
        transactions: list[Transaction] = []

        for item in raw_orders.get("items", []):
            filled_at = _parse_dt(item.get("filledAt") or item.get("dateCreated", ""))
            if filled_at and filled_at < since:
                continue
            ticker = item.get("ticker", "")
            qty = Decimal(str(item.get("filledQuantity", 0)))
            price = Decimal(str(item.get("fillPrice", 0)))
            tx_type = (
                TransactionType.BUY
                if item.get("type") == "BUY"
                else TransactionType.SELL
            )
            transactions.append(
                Transaction(
                    id=f"t212:order:{item.get('id', '')}",
                    account_id=account.id,
                    transaction_type=tx_type,
                    asset=Asset(
                        ticker=ticker,
                        name=ticker,
                        asset_class=AssetClass.EQUITY,
                        currency=account.currency,
                    ),
                    quantity=qty,
                    price=price,
                    fees=Decimal(
                        str(
                            item.get("taxes", [{}])[0].get("fillId", 0)
                            if item.get("taxes")
                            else 0
                        )
                    ),
                    currency=account.currency,
                    settled_at=filled_at or datetime.now(timezone.utc),
                    notes=f"T212 order {item.get('id', '')}",
                )
            )

        for item in raw_dividends.get("items", []):
            paid_at = _parse_dt(item.get("paidOn", ""))
            if paid_at and paid_at < since:
                continue
            ticker = item.get("ticker", "")
            transactions.append(
                Transaction(
                    id=f"t212:div:{item.get('reference', '')}",
                    account_id=account.id,
                    transaction_type=TransactionType.DIVIDEND,
                    asset=Asset(
                        ticker=ticker,
                        name=ticker,
                        asset_class=AssetClass.EQUITY,
                        currency=account.currency,
                    ),
                    quantity=Decimal("0"),
                    price=Decimal(str(item.get("amount", 0))),
                    fees=Decimal("0"),
                    currency=account.currency,
                    settled_at=paid_at or datetime.now(timezone.utc),
                    notes=f"Dividend {ticker}",
                )
            )

        for item in raw_cash.get("items", []):
            tx_time = _parse_dt(item.get("dateTime", ""))
            if tx_time and tx_time < since:
                continue
            amount = Decimal(str(item.get("amount", 0)))
            tx_type = (
                TransactionType.DEPOSIT if amount >= 0 else TransactionType.WITHDRAWAL
            )
            transactions.append(
                Transaction(
                    id=f"t212:cash:{item.get('reference', '')}",
                    account_id=account.id,
                    transaction_type=tx_type,
                    asset=None,
                    quantity=abs(amount),
                    price=Decimal("1"),
                    fees=Decimal("0"),
                    currency=account.currency,
                    settled_at=tx_time or datetime.now(timezone.utc),
                    notes=item.get("type", ""),
                )
            )

        return transactions


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None
