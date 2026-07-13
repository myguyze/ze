from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from ze_logging import get_logger

log = get_logger(__name__)


class FinanceSignalSource:
    """SignalSource for the finance domain.

    Emits signals after each daily snapshot:
    - finance.pnl_swing: total unrealised P&L changed > 5% vs previous snapshot
    - finance.large_transaction: single transaction >= configured threshold
    """

    source_key = "finance"

    def __init__(self, large_tx_threshold: Decimal = Decimal("500")) -> None:
        self._threshold = large_tx_threshold
        self._pending: list[dict] = []
        self._previous_pnl: Decimal | None = None

    def check_pnl_swing(self, current_pnl: Decimal) -> None:
        if self._previous_pnl is not None and self._previous_pnl != 0:
            change_pct = (
                abs((current_pnl - self._previous_pnl) / self._previous_pnl) * 100
            )
            if change_pct > Decimal("5"):
                self._pending.append(
                    {
                        "id": str(uuid.uuid4()),
                        "source": self.source_key,
                        "signal_type": "finance.pnl_swing",
                        "title": "Portfolio P&L swing detected",
                        "summary": (
                            f"Unrealised P&L changed by {change_pct:.1f}% "
                            f"from {self._previous_pnl:.2f} to {current_pnl:.2f}."
                        ),
                        "severity": "medium",
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
        self._previous_pnl = current_pnl

    def check_large_transactions(self, transactions: list, currency: str = "") -> None:
        for tx in transactions:
            notional = tx.quantity * tx.price
            if notional >= self._threshold:
                self._pending.append(
                    {
                        "id": str(uuid.uuid4()),
                        "source": self.source_key,
                        "signal_type": "finance.large_transaction",
                        "title": f"Large transaction: {tx.notes or tx.transaction_type.value}",
                        "summary": (
                            f"{notional:.2f} {tx.currency} — {tx.notes or tx.transaction_type.value}"
                        ),
                        "severity": "low",
                        "occurred_at": tx.settled_at.isoformat()
                        if tx.settled_at
                        else datetime.now(timezone.utc).isoformat(),
                    }
                )

    async def poll(self, since: datetime) -> list[dict]:
        result = self._pending
        self._pending = []
        return result
