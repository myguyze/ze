from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from unittest.mock import AsyncMock, MagicMock

from ze_finance.recurring.detector import RecurringDetector
from ze_finance.recurring.types import cadence_label, snap_interval
from ze_finance.types import Transaction, TransactionType


def _tx(
    notes: str,
    amount: Decimal,
    date: datetime,
    tx_type: TransactionType = TransactionType.WITHDRAWAL,
    currency: str = "EUR",
    account_id: str = "acc1",
) -> Transaction:
    return Transaction(
        id=f"{account_id}:{notes}-{date.isoformat()}",
        account_id=account_id,
        transaction_type=tx_type,
        asset=None,
        quantity=amount,
        price=Decimal("1"),
        fees=Decimal("0"),
        currency=currency,
        settled_at=date,
        notes=notes,
    )


def _dates(start_month: int, interval_days: int, count: int) -> list[datetime]:
    base = datetime(2026, start_month, 1, tzinfo=timezone.utc)
    return [base + timedelta(days=i * interval_days) for i in range(count)]


# ── snap_interval ──────────────────────────────────────────────────────────────

def test_snap_weekly() -> None:
    assert snap_interval(7) == 7
    assert snap_interval(6) == 7
    assert snap_interval(8) == 7


def test_snap_biweekly() -> None:
    assert snap_interval(14) == 14
    assert snap_interval(13) == 14
    assert snap_interval(15) == 14


def test_snap_monthly() -> None:
    assert snap_interval(30) == 30
    assert snap_interval(31) == 30
    assert snap_interval(28) == 28   # 28 is its own natural interval


def test_snap_quarterly() -> None:
    assert snap_interval(90) == 90
    assert snap_interval(88) == 90


def test_snap_bimonthly() -> None:
    assert snap_interval(60) == 60


# ── cadence_label ──────────────────────────────────────────────────────────────

def test_cadence_labels() -> None:
    assert cadence_label(7)   == "weekly"
    assert cadence_label(14)  == "every 2 weeks"
    assert cadence_label(30)  == "monthly"
    assert cadence_label(90)  == "quarterly"
    assert cadence_label(365) == "yearly"
    assert cadence_label(45)  == "every 45 days"


# ── RecurringDetector ──────────────────────────────────────────────────────────

def test_detects_monthly() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [_tx("Netflix Premium", Decimal("15.99"), d) for d in dates]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].interval_days == 30
    assert results[0].amount == Decimal("15.99")
    assert results[0].occurrence_count == 3


def test_detects_weekly() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=7, count=4)
    txs = [_tx("Gym class", Decimal("12.00"), d) for d in dates]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].interval_days == 7


def test_detects_biweekly() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=14, count=3)
    txs = [_tx("Cleaner", Decimal("40.00"), d) for d in dates]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].interval_days == 14
    assert cadence_label(results[0].interval_days) == "every 2 weeks"


def test_detects_quarterly() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=90, count=3)
    txs = [_tx("Adobe Creative Cloud", Decimal("59.99"), d) for d in dates]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].interval_days == 90


def test_rejects_single_occurrence() -> None:
    detector = RecurringDetector()
    txs = [_tx("Netflix", Decimal("15.99"), datetime(2026, 1, 1, tzinfo=timezone.utc))]
    assert detector.detect(txs) == []


def test_rejects_insufficient_span() -> None:
    # Two occurrences 3 days apart are below the 14-day minimum absolute span
    detector = RecurringDetector()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    txs = [
        _tx("Spotify", Decimal("9.99"), base),
        _tx("Spotify", Decimal("9.99"), base + timedelta(days=3)),
    ]
    assert detector.detect(txs) == []


def test_rejects_inconsistent_gaps() -> None:
    # Alternating 7- and 30-day gaps — no clear pattern
    detector = RecurringDetector()
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    dates = [
        base,
        base + timedelta(days=7),
        base + timedelta(days=37),
        base + timedelta(days=44),
    ]
    txs = [_tx("Mystery charge", Decimal("10.00"), d) for d in dates]
    assert detector.detect(txs) == []


def test_rejects_high_amount_variance() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [
        _tx("Bolt Food", Decimal("8.00"), dates[0]),
        _tx("Bolt Food", Decimal("40.00"), dates[1]),
        _tx("Bolt Food", Decimal("12.00"), dates[2]),
    ]
    assert detector.detect(txs) == []


def test_rejects_non_spending_types() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [_tx("Salary", Decimal("3000"), d, tx_type=TransactionType.DEPOSIT) for d in dates]
    assert detector.detect(txs) == []


def test_separates_by_account() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = (
        [_tx("Spotify", Decimal("9.99"), d, account_id="acc1") for d in dates]
        + [_tx("Spotify", Decimal("9.99"), d, account_id="acc2") for d in dates]
    )
    results = detector.detect(txs)
    assert len(results) == 2
    assert {r.account_id for r in results} == {"acc1", "acc2"}


def test_amount_is_median() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [
        _tx("iCloud", Decimal("0.99"), dates[0]),
        _tx("iCloud", Decimal("0.99"), dates[1]),
        _tx("iCloud", Decimal("1.09"), dates[2]),  # within 10% tolerance
    ]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].amount == Decimal("0.99")


def test_normalisation_merges_suffix_digits() -> None:
    detector = RecurringDetector()
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [
        _tx("Netflix 1234", Decimal("15.99"), dates[0]),
        _tx("Netflix 5678", Decimal("15.99"), dates[1]),
        _tx("Netflix 9012", Decimal("15.99"), dates[2]),
    ]
    results = detector.detect(txs)
    assert len(results) == 1


def test_gap_tolerance_allows_month_length_drift() -> None:
    # Monthly charge: Feb=28 days, March=31 days, April=30 days — all within 40% of 30
    detector = RecurringDetector()
    txs = [
        _tx("Rent", Decimal("800"), datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _tx("Rent", Decimal("800"), datetime(2026, 2, 1, tzinfo=timezone.utc)),
        _tx("Rent", Decimal("800"), datetime(2026, 3, 1, tzinfo=timezone.utc)),
        _tx("Rent", Decimal("800"), datetime(2026, 4, 1, tzinfo=timezone.utc)),
    ]
    results = detector.detect(txs)
    assert len(results) == 1
    assert results[0].interval_days == 30  # gaps [31, 28, 31], median=31, snaps to 30 (monthly)


async def test_recurring_merchant_merge() -> None:
    dates = _dates(start_month=1, interval_days=30, count=3)
    txs = [
        _tx("NETFLIX.COM", Decimal("15.99"), dates[0]),
        _tx("Netflix", Decimal("15.99"), dates[1]),
        _tx("NETFLIX SUBSCRIPTION", Decimal("15.99"), dates[2]),
    ]

    embedder = MagicMock()
    embedder.encode.return_value = [
        [1.0, 0.0],
        [0.95, 0.05],
        [0.94, 0.06],
    ]

    nli_client = MagicMock()
    nli_client.scores = AsyncMock(return_value=[
        {"entailment": 0.85, "contradiction": 0.05, "neutral": 0.10},
        {"entailment": 0.82, "contradiction": 0.08, "neutral": 0.10},
        {"entailment": 0.80, "contradiction": 0.10, "neutral": 0.10},
        {"entailment": 0.79, "contradiction": 0.11, "neutral": 0.10},
        {"entailment": 0.81, "contradiction": 0.09, "neutral": 0.10},
        {"entailment": 0.78, "contradiction": 0.12, "neutral": 0.10},
    ])

    detector = RecurringDetector(
        embedder=embedder,
        nli_client=nli_client,
        nli_merchant_merge_enabled=True,
        nli_merchant_cosine_threshold=0.70,
        nli_merchant_entailment_threshold=0.70,
    )

    results = await detector.detect_transactions(txs)
    assert len(results) == 1
    assert results[0].occurrence_count == 3
