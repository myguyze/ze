from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import asyncpg

from ze_agents.logging import get_logger
from ze_finance.types import (
    Account,
    AccountType,
    Asset,
    AssetClass,
    CsvMapping,
    Position,
    SpendingSummary,
    Transaction,
    TransactionType,
)

log = get_logger(__name__)


class PortfolioStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_account(self, account: Account) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO finance_accounts (id, source_id, account_type, name, currency, balance, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET
                    source_id    = EXCLUDED.source_id,
                    account_type = EXCLUDED.account_type,
                    name         = EXCLUDED.name,
                    currency     = EXCLUDED.currency,
                    balance      = EXCLUDED.balance,
                    updated_at   = EXCLUDED.updated_at
                """,
                account.id,
                account.source_id,
                account.account_type.value,
                account.name,
                account.currency,
                str(account.balance),
                account.updated_at,
            )

    async def upsert_positions(self, positions: list[Position]) -> None:
        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO finance_positions
                    (account_id, ticker, asset_name, asset_class, quantity, notional,
                     average_price, current_price, unrealised_pnl, currency, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (account_id, ticker) DO UPDATE SET
                    asset_name     = EXCLUDED.asset_name,
                    asset_class    = EXCLUDED.asset_class,
                    quantity       = EXCLUDED.quantity,
                    notional       = EXCLUDED.notional,
                    average_price  = EXCLUDED.average_price,
                    current_price  = EXCLUDED.current_price,
                    unrealised_pnl = EXCLUDED.unrealised_pnl,
                    currency       = EXCLUDED.currency,
                    updated_at     = EXCLUDED.updated_at
                """,
                [
                    (
                        p.account_id,
                        p.asset.ticker,
                        p.asset.name,
                        p.asset.asset_class.value,
                        str(p.quantity),
                        str(p.notional),
                        str(p.average_price),
                        str(p.current_price),
                        str(p.unrealised_pnl),
                        p.currency,
                        p.updated_at,
                    )
                    for p in positions
                ],
            )

    async def get_positions(self, account_id: str | None = None) -> list[Position]:
        async with self._pool.acquire() as conn:
            if account_id:
                rows = await conn.fetch(
                    "SELECT * FROM finance_positions WHERE account_id = $1 ORDER BY notional DESC",
                    account_id,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM finance_positions ORDER BY account_id, notional DESC"
                )
        return [_row_to_position(r) for r in rows]

    async def get_account(self, account_id: str) -> Account | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM finance_accounts WHERE id = $1", account_id
            )
        return _row_to_account(row) if row else None

    async def list_accounts(self) -> list[Account]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM finance_accounts ORDER BY id")
        return [_row_to_account(r) for r in rows]


class TransactionStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def append(self, transactions: list[Transaction]) -> int:
        if not transactions:
            return 0
        inserted = 0
        async with self._pool.acquire() as conn:
            for tx in transactions:
                external_id = tx.id.split(":", 1)[-1] if ":" in tx.id else tx.id
                result = await conn.execute(
                    """
                    INSERT INTO finance_transactions
                        (external_id, account_id, transaction_type, ticker, asset_name, asset_class,
                         quantity, price, fees, currency, settled_at, notes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (account_id, external_id) DO NOTHING
                    """,
                    external_id,
                    tx.account_id,
                    tx.transaction_type.value,
                    tx.asset.ticker if tx.asset else None,
                    tx.asset.name if tx.asset else None,
                    tx.asset.asset_class.value if tx.asset else None,
                    str(tx.quantity),
                    str(tx.price),
                    str(tx.fees),
                    tx.currency,
                    tx.settled_at,
                    tx.notes,
                )
                if result == "INSERT 0 1":
                    inserted += 1
        return inserted

    async def get(
        self,
        account_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[Transaction]:
        conditions = []
        params: list = []
        idx = 1
        if account_id:
            conditions.append(f"account_id = ${idx}")
            params.append(account_id)
            idx += 1
        if since:
            conditions.append(f"settled_at >= ${idx}")
            params.append(since)
            idx += 1
        if until:
            conditions.append(f"settled_at <= ${idx}")
            params.append(until)
            idx += 1
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)
        query = f"SELECT * FROM finance_transactions {where} ORDER BY settled_at DESC LIMIT ${idx}"
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [_row_to_transaction(r) for r in rows]

    async def spending_by_category(
        self,
        since: datetime,
        until: datetime,
        account_id: str | None = None,
    ) -> list[SpendingSummary]:
        conditions = ["settled_at >= $1", "settled_at <= $2", "transaction_type IN ('deposit', 'withdrawal', 'fee')"]
        params: list = [since, until]
        idx = 3
        if account_id:
            conditions.append(f"account_id = ${idx}")
            params.append(account_id)
        where = "WHERE " + " AND ".join(conditions)
        query = f"""
            SELECT
                COALESCE(category, 'Other') AS category,
                currency,
                SUM(ABS(price * quantity)) AS total,
                COUNT(*) AS transaction_count
            FROM finance_transactions
            {where}
            GROUP BY COALESCE(category, 'Other'), currency
            ORDER BY total DESC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [
            SpendingSummary(
                category=r["category"],
                total=Decimal(str(r["total"])),
                currency=r["currency"],
                transaction_count=r["transaction_count"],
            )
            for r in rows
        ]

    async def get_last_settled_at(self, account_id: str) -> datetime | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT MAX(settled_at) AS last_at FROM finance_transactions WHERE account_id = $1",
                account_id,
            )
        if row and row["last_at"]:
            return row["last_at"]
        return None

    async def update_category(self, external_id: str, account_id: str, category: str, source: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE finance_transactions
                SET category = $1, category_source = $2
                WHERE external_id = $3 AND account_id = $4
                """,
                category,
                source,
                external_id,
                account_id,
            )


class CsvMappingStore:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get(self, source_id: str) -> CsvMapping | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM finance_csv_mappings WHERE source_id = $1", source_id
            )
        return _row_to_csv_mapping(row) if row else None

    async def upsert(self, source_id: str, mapping: CsvMapping) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO finance_csv_mappings
                    (source_id, date_column, amount_column, debit_column, credit_column,
                     description_column, currency_column, date_format, inferred_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (source_id) DO UPDATE SET
                    date_column        = EXCLUDED.date_column,
                    amount_column      = EXCLUDED.amount_column,
                    debit_column       = EXCLUDED.debit_column,
                    credit_column      = EXCLUDED.credit_column,
                    description_column = EXCLUDED.description_column,
                    currency_column    = EXCLUDED.currency_column,
                    date_format        = EXCLUDED.date_format,
                    inferred_at        = EXCLUDED.inferred_at
                """,
                source_id,
                mapping.date_column,
                mapping.amount_column or None,
                mapping.debit_column,
                mapping.credit_column,
                mapping.description_column,
                mapping.currency_column,
                mapping.date_format,
                mapping.inferred_at,
            )

    async def delete(self, source_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM finance_csv_mappings WHERE source_id = $1", source_id
            )


def _row_to_account(row: asyncpg.Record) -> Account:
    return Account(
        id=row["id"],
        source_id=row["source_id"],
        account_type=AccountType(row["account_type"]),
        name=row["name"],
        currency=row["currency"],
        balance=Decimal(str(row["balance"])),
        updated_at=row["updated_at"],
    )


def _row_to_position(row: asyncpg.Record) -> Position:
    asset = Asset(
        ticker=row["ticker"],
        name=row["asset_name"],
        asset_class=AssetClass(row["asset_class"]),
        currency=row["currency"],
    )
    return Position(
        account_id=row["account_id"],
        asset=asset,
        quantity=Decimal(str(row["quantity"])),
        notional=Decimal(str(row["notional"])),
        average_price=Decimal(str(row["average_price"])),
        current_price=Decimal(str(row["current_price"])),
        unrealised_pnl=Decimal(str(row["unrealised_pnl"])),
        currency=row["currency"],
        updated_at=row["updated_at"],
    )


def _row_to_transaction(row: asyncpg.Record) -> Transaction:
    asset = None
    if row["ticker"]:
        asset = Asset(
            ticker=row["ticker"],
            name=row["asset_name"] or row["ticker"],
            asset_class=AssetClass(row["asset_class"]) if row["asset_class"] else AssetClass.EQUITY,
            currency=row["currency"],
        )
    return Transaction(
        id=f"{row['account_id']}:{row['external_id']}",
        account_id=row["account_id"],
        transaction_type=TransactionType(row["transaction_type"]),
        asset=asset,
        quantity=Decimal(str(row["quantity"])),
        price=Decimal(str(row["price"])),
        fees=Decimal(str(row["fees"])),
        currency=row["currency"],
        settled_at=row["settled_at"],
        notes=row["notes"] or "",
    )


def _row_to_csv_mapping(row: asyncpg.Record) -> CsvMapping:
    return CsvMapping(
        source_id=row["source_id"],
        date_column=row["date_column"],
        amount_column=row["amount_column"] or "",
        description_column=row["description_column"],
        date_format=row["date_format"],
        debit_column=row["debit_column"],
        credit_column=row["credit_column"],
        currency_column=row["currency_column"],
        inferred_at=row["inferred_at"],
    )
