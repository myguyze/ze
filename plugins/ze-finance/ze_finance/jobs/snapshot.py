from __future__ import annotations

from datetime import datetime, timezone, timedelta

from ze_logging import get_logger
from ze_finance.categoriser import CategoryInferrer
from ze_finance.signals.finance import FinanceSignalSource
from ze_finance.source import DataSource
from ze_finance.store import PortfolioStore, TransactionStore
from ze_proactive.job import proactive_job

log = get_logger(__name__)


@proactive_job
class DailySnapshotJob:
    """Syncs positions and transactions from all configured data sources."""

    job_id = "finance.daily_snapshot"

    def __init__(
        self,
        sources: list[DataSource],
        portfolio_store: PortfolioStore,
        transaction_store: TransactionStore,
        signal_source: FinanceSignalSource,
        categoriser: CategoryInferrer,
    ) -> None:
        self._sources = sources
        self._portfolio = portfolio_store
        self._transactions = transaction_store
        self._signals = signal_source
        self._categoriser = categoriser

    async def run(self) -> None:
        for source in self._sources:
            try:
                await self._sync_source(source)
            except Exception as exc:
                log.error("finance_snapshot_failed", source=source.source_id, error=str(exc))

        positions = await self._portfolio.get_positions()
        total_pnl = sum(p.unrealised_pnl for p in positions)
        self._signals.check_pnl_swing(total_pnl)

    async def _sync_source(self, source: DataSource) -> None:
        account = await source.fetch_account()
        await self._portfolio.upsert_account(account)

        positions = await source.fetch_positions()
        if positions:
            await self._portfolio.upsert_positions(positions)

        last_at = await self._transactions.get_last_settled_at(account.id)
        since = last_at or datetime.now(timezone.utc) - timedelta(days=90)
        new_txs = await source.fetch_transactions(since=since)
        inserted = await self._transactions.append(new_txs)

        descriptions = [tx.notes for tx in new_txs if tx.notes]
        if descriptions:
            categories = await self._categoriser.infer_batch(descriptions)
            for tx, category in zip(new_txs, categories):
                if tx.notes:
                    external_id = tx.id.split(":", 1)[-1] if ":" in tx.id else tx.id
                    source_label = "keyword" if category != "Other" else "keyword"
                    await self._transactions.update_category(external_id, tx.account_id, category, source_label)

        self._signals.check_large_transactions(new_txs)
        log.info(
            "finance_snapshot_synced",
            source=source.source_id,
            account=account.id,
            positions=len(positions),
            transactions_inserted=inserted,
        )
