from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ze_finance.recurring.store import RecurringStore
from ze_finance.recurring.types import RecurringExpense, RecurringStatus


def _expense(
    key: str = "netflix",
    amount: Decimal = Decimal("15.99"),
    status: RecurringStatus = RecurringStatus.DETECTED,
    previous_amount: Decimal | None = None,
) -> RecurringExpense:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return RecurringExpense(
        normalised_key=key,
        account_id="acc1",
        merchant_display="Netflix",
        amount=amount,
        currency="EUR",
        interval_days=30,
        category="Entertainment",
        status=status,
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=3,
        previous_amount=previous_amount,
    )


def _mock_pool(fetchrow_return=None, fetch_return=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=ctx)
    return pool, conn


@pytest.mark.asyncio
async def test_upsert_new_candidate() -> None:
    pool, conn = _mock_pool(fetchrow_return=None)
    store = RecurringStore(pool=pool)

    result = await store.upsert_detected([_expense()])

    assert len(result.new_candidates) == 1
    assert result.price_changed == []
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args[0][0]
    assert "INSERT INTO finance_recurring" in call_sql


@pytest.mark.asyncio
async def test_upsert_confirmed_updates_amount_only() -> None:
    row = {"status": "confirmed", "amount": "15.99"}
    pool, conn = _mock_pool(fetchrow_return=row)
    store = RecurringStore(pool=pool)

    result = await store.upsert_detected([_expense(amount=Decimal("16.50"))])

    assert result.new_candidates == []
    assert result.price_changed == []
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args[0][0]
    assert "UPDATE finance_recurring" in call_sql
    assert "status" not in call_sql.lower().split("set")[1].split("where")[0]


@pytest.mark.asyncio
async def test_upsert_dismissed_small_change_stays_dismissed() -> None:
    row = {"status": "dismissed", "amount": "15.99"}
    pool, conn = _mock_pool(fetchrow_return=row)
    store = RecurringStore(pool=pool, price_change_threshold=0.10)

    # 5% change — below threshold
    result = await store.upsert_detected([_expense(amount=Decimal("16.79"))])

    assert result.new_candidates == []
    assert result.price_changed == []
    # Should only touch last_seen_at
    conn.execute.assert_called_once()
    call_sql = conn.execute.call_args[0][0]
    assert "last_seen_at" in call_sql
    assert "status" not in call_sql


@pytest.mark.asyncio
async def test_upsert_dismissed_large_change_resurfaces() -> None:
    row = {"status": "dismissed", "amount": "15.99"}
    pool, conn = _mock_pool(fetchrow_return=row)
    store = RecurringStore(pool=pool, price_change_threshold=0.10)

    # 15% increase — above threshold
    result = await store.upsert_detected([_expense(amount=Decimal("18.39"))])

    assert result.new_candidates == []
    assert len(result.price_changed) == 1
    changed = result.price_changed[0]
    assert changed.previous_amount == Decimal("15.99")
    assert changed.amount == Decimal("18.39")
    assert changed.status == RecurringStatus.DETECTED
    # Status should have been reset to detected ($1 arg in the UPDATE call)
    call_args = conn.execute.call_args[0]
    assert call_args[1] == RecurringStatus.DETECTED.value
