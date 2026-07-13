from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class RecurringStatus(str, Enum):
    DETECTED = "detected"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


# Natural billing intervals in days, ordered for snapping.
_NATURAL_INTERVALS: list[int] = [1, 7, 14, 21, 28, 30, 42, 60, 90, 120, 180, 365]

_CADENCE_LABELS: dict[int, str] = {
    1: "daily",
    7: "weekly",
    14: "every 2 weeks",
    21: "every 3 weeks",
    28: "every 4 weeks",
    30: "monthly",
    42: "every 6 weeks",
    60: "every 2 months",
    90: "quarterly",
    120: "every 4 months",
    180: "every 6 months",
    365: "yearly",
}


def cadence_label(interval_days: int) -> str:
    if interval_days in _CADENCE_LABELS:
        return _CADENCE_LABELS[interval_days]
    return f"every {interval_days} days"


def snap_interval(days: int) -> int:
    """Snap a raw gap in days to the nearest natural billing interval."""
    return min(_NATURAL_INTERVALS, key=lambda n: abs(n - days))


@dataclass
class RecurringExpense:
    normalised_key: str
    account_id: str
    merchant_display: str
    amount: Decimal
    currency: str
    interval_days: int  # snapped to nearest natural interval
    category: str
    status: RecurringStatus
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int
    previous_amount: Decimal | None = None  # set on price-change resurfaces


@dataclass
class StalenessReport:
    account_id: str
    is_stale: bool
    days_since_last: int
    last_transaction_at: datetime | None


@dataclass
class UpsertResult:
    new_candidates: list[RecurringExpense]
    price_changed: list[RecurringExpense]
