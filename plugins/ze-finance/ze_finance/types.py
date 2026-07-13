from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    CASH = "cash"
    OPTION = "option"  # reserved; not handled in Phase 67


class AccountType(str, Enum):
    BROKERAGE = "brokerage"
    BANK = "bank"
    CRYPTO = "crypto"
    ISA = "isa"


class TransactionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"


@dataclass(frozen=True)
class Asset:
    ticker: str
    name: str
    asset_class: AssetClass
    currency: str


@dataclass
class Account:
    id: str
    source_id: str
    account_type: AccountType
    name: str
    currency: str
    balance: Decimal
    updated_at: datetime


@dataclass
class Position:
    account_id: str
    asset: Asset
    quantity: Decimal
    # notional is the authoritative aggregation unit — quantity × current_price.
    # The risk engine uses this field directly; never aggregate on quantity.
    notional: Decimal
    average_price: Decimal
    current_price: Decimal
    unrealised_pnl: Decimal
    currency: str
    updated_at: datetime


@dataclass
class Transaction:
    id: str
    account_id: str
    transaction_type: TransactionType
    asset: Asset | None
    quantity: Decimal
    price: Decimal
    fees: Decimal
    currency: str
    settled_at: datetime
    notes: str = ""


@dataclass
class SpendingSummary:
    """Aggregated output for data-minimised tool responses."""

    category: str
    total: Decimal
    currency: str
    transaction_count: int


@dataclass
class CsvMapping:
    """Persisted column mapping for a specific bank CSV format."""

    source_id: str
    date_column: str
    amount_column: str
    description_column: str
    date_format: str
    debit_column: str | None = None
    credit_column: str | None = None
    currency_column: str | None = None
    inferred_at: datetime = field(default_factory=datetime.utcnow)
