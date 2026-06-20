from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal
from datetime import datetime

from ze_finance.recurring.types import RecurringExpense, RecurringStatus, snap_interval
from ze_finance.types import Transaction, TransactionType

_MIN_OCCURRENCES     = 2   # minimum number of transactions to consider
_AMOUNT_TOLERANCE    = 0.10  # max coefficient of variation on amounts
_GAP_TOLERANCE       = 0.40  # gaps must be within ±40% of the median gap
                              # (billing dates drift; months differ in length)
_MIN_SPAN_FACTOR     = 1.5   # total date span must be ≥ 1.5× detected interval
_MIN_ABSOLUTE_SPAN   = 14    # span must be at least 14 days regardless of interval


def _normalise(description: str) -> str:
    s = description.lower()
    s = re.sub(r"\d+", "", s)
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _median_decimal(values: list[Decimal]) -> Decimal:
    sorted_vals = sorted(values)
    mid = len(sorted_vals) // 2
    if len(sorted_vals) % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2


def _detect_interval(dates: list[datetime]) -> int | None:
    """
    Derive the dominant billing interval from a sorted list of occurrence dates.

    Returns the snapped interval in days, or None if no consistent pattern exists.
    Gaps must all be within ±GAP_TOLERANCE of the median gap, which filters out
    merchants with erratic timing (e.g. alternating weekly/monthly charges).
    """
    sorted_dates = sorted(dates)
    gaps = [
        (sorted_dates[i + 1] - sorted_dates[i]).days
        for i in range(len(sorted_dates) - 1)
    ]
    if not gaps:
        return None

    sorted_gaps = sorted(gaps)
    median_gap = sorted_gaps[len(sorted_gaps) // 2]
    if median_gap < 1:
        return None

    # Reject if any gap falls outside the tolerance band around the median.
    for g in gaps:
        if abs(g - median_gap) / median_gap > _GAP_TOLERANCE:
            return None

    return snap_interval(median_gap)


class RecurringDetector:
    """Pure, stateless detector — no I/O."""

    _SPENDING_TYPES = {TransactionType.WITHDRAWAL, TransactionType.FEE}

    def detect(self, transactions: list[Transaction]) -> list[RecurringExpense]:
        spending = [
            tx for tx in transactions
            if tx.transaction_type in self._SPENDING_TYPES and tx.notes
        ]

        groups: dict[tuple[str, str, str], list[Transaction]] = {}
        for tx in spending:
            key = (_normalise(tx.notes), tx.currency, tx.account_id)
            groups.setdefault(key, []).append(tx)

        results: list[RecurringExpense] = []
        for (norm_key, currency, account_id), txs in groups.items():
            if len(txs) < _MIN_OCCURRENCES:
                continue

            sorted_txs = sorted(txs, key=lambda t: t.settled_at)

            interval_days = _detect_interval([tx.settled_at for tx in sorted_txs])
            if interval_days is None:
                continue

            # Enough history to confirm the pattern completed at least once.
            span = (sorted_txs[-1].settled_at - sorted_txs[0].settled_at).days
            if span < max(interval_days * _MIN_SPAN_FACTOR, _MIN_ABSOLUTE_SPAN):
                continue

            amounts = [abs(tx.quantity * tx.price) for tx in txs]
            mean_amount = sum(amounts) / len(amounts)
            if mean_amount == 0:
                continue

            variance = sum((a - mean_amount) ** 2 for a in amounts) / len(amounts)
            cv = (variance ** Decimal("0.5")) / mean_amount
            if cv > Decimal(str(_AMOUNT_TOLERANCE)):
                continue

            display = Counter(tx.notes for tx in txs).most_common(1)[0][0]
            median_amount = _median_decimal(amounts)

            results.append(
                RecurringExpense(
                    normalised_key=norm_key,
                    account_id=account_id,
                    merchant_display=display,
                    amount=median_amount.quantize(Decimal("0.01")),
                    currency=currency,
                    interval_days=interval_days,
                    category="Other",
                    status=RecurringStatus.DETECTED,
                    first_seen_at=sorted_txs[0].settled_at,
                    last_seen_at=sorted_txs[-1].settled_at,
                    occurrence_count=len(txs),
                )
            )

        return results
