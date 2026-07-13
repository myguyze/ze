from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ze_logging import get_logger
from ze_proactive.job import proactive_job
from ze_proactive.notifier import ProactiveNotifier
from ze_finance.recurring.detector import RecurringDetector
from ze_finance.recurring.store import RecurringStore
from ze_finance.recurring.types import RecurringExpense, StalenessReport, cadence_label
from ze_finance.store import PortfolioStore, TransactionStore

log = get_logger(__name__)


@proactive_job
class RecurringDetectionJob:
    job_id = "finance.recurring_detection"

    def __init__(
        self,
        portfolio_store: PortfolioStore,
        transaction_store: TransactionStore,
        recurring_store: RecurringStore,
        notifier: ProactiveNotifier,
        detector: RecurringDetector,
        staleness_days: int = 35,
        nudge_cooldown_days: int = 14,
        lookback_days: int = 90,
    ) -> None:
        self._portfolio = portfolio_store
        self._transactions = transaction_store
        self._recurring = recurring_store
        self._notifier = notifier
        self._detector = detector
        self._staleness_days = staleness_days
        self._nudge_cooldown_days = nudge_cooldown_days
        self._lookback_days = lookback_days

    async def run(self) -> None:
        accounts = await self._portfolio.list_accounts()
        for account in accounts:
            try:
                report = await self._staleness_report(account.id)
                if report.is_stale:
                    await self._handle_stale(account, report)
                else:
                    await self._detect_and_surface(account.id)
            except Exception:
                log.exception("recurring_detection_failed", account_id=account.id)

    async def _staleness_report(self, account_id: str) -> StalenessReport:
        last_at = await self._transactions.get_last_settled_at(account_id)
        if last_at is None:
            return StalenessReport(
                account_id=account_id,
                is_stale=True,
                days_since_last=0,
                last_transaction_at=None,
            )
        now = datetime.now(timezone.utc)
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        days = (now - last_at).days
        return StalenessReport(
            account_id=account_id,
            is_stale=days > self._staleness_days,
            days_since_last=days,
            last_transaction_at=last_at,
        )

    async def _handle_stale(self, account, report: StalenessReport) -> None:
        if not account.source_id.startswith("csv:"):
            log.error(
                "finance_live_source_stale",
                account_id=account.id,
                source_id=account.source_id,
                days_since_last=report.days_since_last,
            )
            return

        # Rate-limit nudges per account.
        last_nudge = await self._recurring.get_last_nudge_at(account.id)
        if last_nudge is not None:
            if last_nudge.tzinfo is None:
                last_nudge = last_nudge.replace(tzinfo=timezone.utc)
            days_since_nudge = (datetime.now(timezone.utc) - last_nudge).days
            if days_since_nudge < self._nudge_cooldown_days:
                log.info(
                    "finance_stale_nudge_suppressed",
                    account_id=account.id,
                    days_since_nudge=days_since_nudge,
                )
                return

        days_label = (
            f"{report.days_since_last} days"
            if report.days_since_last > 0
            else "a while"
        )
        await self._notifier.push(
            f"I haven't seen new transactions for '{account.name}' in {days_label}. "
            "Upload a fresh bank statement so I can keep your recurring expense list up to date."
        )
        await self._recurring.record_nudge(account.id)
        log.info("finance_stale_nudge_sent", account_id=account.id)

    async def _detect_and_surface(self, account_id: str) -> None:
        since = datetime.now(timezone.utc) - timedelta(days=self._lookback_days)
        transactions = await self._transactions.get(account_id=account_id, since=since)

        candidates = await self._detector.detect_transactions(transactions)
        if not candidates:
            return

        result = await self._recurring.upsert_detected(candidates)

        if result.new_candidates:
            body = _format_new_summary(result.new_candidates)
            await self._notifier.push(body)
            log.info(
                "finance_recurring_new_candidates",
                account_id=account_id,
                count=len(result.new_candidates),
            )

        for item in result.price_changed:
            prev = f"{item.currency} {item.previous_amount}"
            curr = f"{item.currency} {item.amount}"
            await self._notifier.push(
                f"Your {item.merchant_display} charge changed from {prev} to {curr} — "
                "still happy with it?"
            )
            log.info(
                "finance_recurring_price_changed",
                account_id=account_id,
                merchant=item.merchant_display,
                previous_amount=str(item.previous_amount),
                new_amount=str(item.amount),
            )


def _format_new_summary(candidates: list[RecurringExpense]) -> str:
    count = len(candidates)
    if count == 1:
        item = candidates[0]
        return (
            f"I spotted a new recurring charge: {item.merchant_display} "
            f"{item.currency} {item.amount} ({cadence_label(item.interval_days)}). "
            "Is this a subscription you want to track?"
        )
    lines = [f"I spotted {count} new recurring charges:"]
    for item in candidates[:5]:
        lines.append(
            f"  • {item.merchant_display} — {item.currency} {item.amount} ({cadence_label(item.interval_days)})"
        )
    if count > 5:
        lines.append(f"  … and {count - 5} more")
    lines.append("Want me to categorise these as subscriptions?")
    return "\n".join(lines)
