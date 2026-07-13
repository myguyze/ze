from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from ze_finance.types import (
    Asset,
    AssetClass,
    Position,
    Transaction,
    TransactionType,
)


def test_asset_frozen():
    a = Asset(
        ticker="NVDA", name="NVIDIA", asset_class=AssetClass.EQUITY, currency="USD"
    )
    assert a.ticker == "NVDA"


def test_position_notional():
    asset = Asset(
        ticker="AAPL", name="Apple", asset_class=AssetClass.EQUITY, currency="USD"
    )
    pos = Position(
        account_id="acc1",
        asset=asset,
        quantity=Decimal("10"),
        notional=Decimal("1750.00"),
        average_price=Decimal("150.00"),
        current_price=Decimal("175.00"),
        unrealised_pnl=Decimal("250.00"),
        currency="USD",
        updated_at=datetime.now(timezone.utc),
    )
    assert pos.notional == Decimal("1750.00")


def test_transaction_no_asset():
    tx = Transaction(
        id="t1",
        account_id="acc1",
        transaction_type=TransactionType.DEPOSIT,
        asset=None,
        quantity=Decimal("500"),
        price=Decimal("1"),
        fees=Decimal("0"),
        currency="EUR",
        settled_at=datetime.now(timezone.utc),
    )
    assert tx.asset is None
    assert tx.transaction_type == TransactionType.DEPOSIT
