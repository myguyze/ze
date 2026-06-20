from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import asyncpg

from ze_agents.logging import get_logger
from ze_finance.recurring.types import (
    RecurringExpense,
    RecurringStatus,
    UpsertResult,
)

log = get_logger(__name__)


class RecurringStore:
    def __init__(self, pool: asyncpg.Pool, price_change_threshold: float = 0.10) -> None:
        self._pool = pool
        self._threshold = Decimal(str(price_change_threshold))

    async def upsert_detected(self, candidates: list[RecurringExpense]) -> UpsertResult:
        new_candidates: list[RecurringExpense] = []
        price_changed: list[RecurringExpense] = []

        async with self._pool.acquire() as conn:
            for candidate in candidates:
                row = await conn.fetchrow(
                    "SELECT status, amount FROM finance_recurring "
                    "WHERE normalised_key = $1 AND account_id = $2",
                    candidate.normalised_key,
                    candidate.account_id,
                )
                if row is None:
                    await conn.execute(
                        """
                        INSERT INTO finance_recurring
                            (normalised_key, account_id, merchant_display, amount, currency,
                             interval_days, category, status, first_seen_at, last_seen_at,
                             occurrence_count)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                        """,
                        candidate.normalised_key,
                        candidate.account_id,
                        candidate.merchant_display,
                        str(candidate.amount),
                        candidate.currency,
                        candidate.interval_days,
                        candidate.category,
                        RecurringStatus.DETECTED.value,
                        candidate.first_seen_at,
                        candidate.last_seen_at,
                        candidate.occurrence_count,
                    )
                    new_candidates.append(candidate)

                elif row["status"] == RecurringStatus.CONFIRMED.value:
                    await conn.execute(
                        """
                        UPDATE finance_recurring
                        SET amount = $1, last_seen_at = $2, occurrence_count = $3,
                            merchant_display = $4, interval_days = $5
                        WHERE normalised_key = $6 AND account_id = $7
                        """,
                        str(candidate.amount),
                        candidate.last_seen_at,
                        candidate.occurrence_count,
                        candidate.merchant_display,
                        candidate.interval_days,
                        candidate.normalised_key,
                        candidate.account_id,
                    )

                elif row["status"] == RecurringStatus.DISMISSED.value:
                    stored_amount = Decimal(str(row["amount"]))
                    change = (
                        abs(candidate.amount - stored_amount) / stored_amount
                        if stored_amount > 0
                        else Decimal("0")
                    )
                    if change > self._threshold:
                        await conn.execute(
                            """
                            UPDATE finance_recurring
                            SET status = $1, amount = $2, last_seen_at = $3,
                                occurrence_count = $4, merchant_display = $5,
                                interval_days = $6
                            WHERE normalised_key = $7 AND account_id = $8
                            """,
                            RecurringStatus.DETECTED.value,
                            str(candidate.amount),
                            candidate.last_seen_at,
                            candidate.occurrence_count,
                            candidate.merchant_display,
                            candidate.interval_days,
                            candidate.normalised_key,
                            candidate.account_id,
                        )
                        price_changed.append(
                            RecurringExpense(
                                normalised_key=candidate.normalised_key,
                                account_id=candidate.account_id,
                                merchant_display=candidate.merchant_display,
                                amount=candidate.amount,
                                currency=candidate.currency,
                                interval_days=candidate.interval_days,
                                category=candidate.category,
                                status=RecurringStatus.DETECTED,
                                first_seen_at=candidate.first_seen_at,
                                last_seen_at=candidate.last_seen_at,
                                occurrence_count=candidate.occurrence_count,
                                previous_amount=stored_amount,
                            )
                        )
                    else:
                        await conn.execute(
                            "UPDATE finance_recurring SET last_seen_at = $1 "
                            "WHERE normalised_key = $2 AND account_id = $3",
                            candidate.last_seen_at,
                            candidate.normalised_key,
                            candidate.account_id,
                        )

        return UpsertResult(new_candidates=new_candidates, price_changed=price_changed)

    async def list(
        self,
        status: RecurringStatus | None = None,
    ) -> list[RecurringExpense]:
        async with self._pool.acquire() as conn:
            if status is not None:
                rows = await conn.fetch(
                    "SELECT * FROM finance_recurring WHERE status = $1 ORDER BY amount DESC",
                    status.value,
                )
            else:
                rows = await conn.fetch(
                    "SELECT * FROM finance_recurring ORDER BY status, amount DESC"
                )
        return [_row_to_expense(r) for r in rows]

    async def confirm(self, normalised_key: str, account_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE finance_recurring SET status = $1 "
                "WHERE normalised_key = $2 AND account_id = $3",
                RecurringStatus.CONFIRMED.value,
                normalised_key,
                account_id,
            )

    async def dismiss(self, normalised_key: str, account_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE finance_recurring SET status = $1 "
                "WHERE normalised_key = $2 AND account_id = $3",
                RecurringStatus.DISMISSED.value,
                normalised_key,
                account_id,
            )

    async def get_last_nudge_at(self, account_id: str) -> datetime | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT last_nudge_at FROM finance_recurring_staleness WHERE account_id = $1",
                account_id,
            )
        return row["last_nudge_at"] if row else None

    async def record_nudge(self, account_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO finance_recurring_staleness (account_id, last_nudge_at)
                VALUES ($1, $2)
                ON CONFLICT (account_id) DO UPDATE SET last_nudge_at = EXCLUDED.last_nudge_at
                """,
                account_id,
                datetime.now(timezone.utc),
            )


def _row_to_expense(row: asyncpg.Record) -> RecurringExpense:
    return RecurringExpense(
        normalised_key=row["normalised_key"],
        account_id=row["account_id"],
        merchant_display=row["merchant_display"],
        amount=Decimal(str(row["amount"])),
        currency=row["currency"],
        interval_days=row["interval_days"],
        category=row["category"],
        status=RecurringStatus(row["status"]),
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        occurrence_count=row["occurrence_count"],
    )
