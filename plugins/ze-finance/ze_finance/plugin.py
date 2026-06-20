from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_agents.settings import Settings as CoreSettings
from ze_proactive.notifier import ProactiveNotifier
from ze_sdk import ZePlugin, DataDomain

log = get_logger(__name__)


class FinancePlugin(ZePlugin):
    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        settings: CoreSettings,
        openrouter_client: LLMClient,
        notifier: ProactiveNotifier,
        trading212_client: Any = None,
    ) -> None:
        from ze_finance.store import PortfolioStore, TransactionStore, CsvMappingStore
        from ze_finance.categoriser import CategoryInferrer
        from ze_finance.signals.finance import FinanceSignalSource
        from ze_finance.jobs.snapshot import DailySnapshotJob
        from ze_finance.jobs.recurring import RecurringDetectionJob
        from ze_finance.sources.csv import CsvSchemaInferrer
        from ze_finance.ingestion.extractor import FinanceIngestionExtractor
        from ze_finance.recurring.detector import RecurringDetector
        from ze_finance.recurring.store import RecurringStore

        fin_cfg = settings.config.get("finance", {})
        self._snapshot_cron: str = fin_cfg.get("snapshot_schedule", "0 8 * * *")
        self._recurring_cron: str = fin_cfg.get("recurring_detection_schedule", "0 9 1 * *")
        self._recurring_enabled: bool = bool(fin_cfg.get("recurring_detection_enabled", False))
        large_tx_threshold = Decimal(str(fin_cfg.get("large_transaction_threshold", 500)))
        llm_cat_enabled: bool = bool(fin_cfg.get("llm_categorization", False))
        staleness_days: int = int(fin_cfg.get("recurring_staleness_days", 35))
        nudge_cooldown_days: int = int(fin_cfg.get("recurring_nudge_cooldown_days", 14))
        price_change_threshold: float = float(fin_cfg.get("recurring_price_change_threshold", 0.10))

        self._portfolio_store = PortfolioStore(pool=pool)
        self._transaction_store = TransactionStore(pool=pool)
        self._csv_mapping_store = CsvMappingStore(pool=pool)
        self._recurring_store = RecurringStore(
            pool=pool,
            price_change_threshold=price_change_threshold,
        )

        self._categoriser = CategoryInferrer(
            client=openrouter_client if llm_cat_enabled else None,
            llm_enabled=llm_cat_enabled,
        )
        self._signal_source = FinanceSignalSource(large_tx_threshold=large_tx_threshold)

        ingestion_model = settings.config.get("models", {}).get("finance_ingestion", "anthropic/claude-haiku-4-5")
        csv_inferrer = CsvSchemaInferrer(client=openrouter_client, mapping_store=self._csv_mapping_store)
        self._ingestion_extractor = FinanceIngestionExtractor(
            transaction_store=self._transaction_store,
            llm_client=openrouter_client,
            model=ingestion_model,
            csv_inferrer=csv_inferrer,
        )

        sources = []
        if trading212_client is not None:
            from ze_finance.sources.trading212 import Trading212DataSource
            sources.append(Trading212DataSource(client=trading212_client))
        else:
            log.info("finance_trading212_not_configured")

        self._snapshot_job = DailySnapshotJob(
            sources=sources,
            portfolio_store=self._portfolio_store,
            transaction_store=self._transaction_store,
            signal_source=self._signal_source,
            categoriser=self._categoriser,
        )
        self._recurring_job = RecurringDetectionJob(
            portfolio_store=self._portfolio_store,
            transaction_store=self._transaction_store,
            recurring_store=self._recurring_store,
            notifier=notifier,
            detector=RecurringDetector(),
            staleness_days=staleness_days,
            nudge_cooldown_days=nudge_cooldown_days,
        )

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_trading212.client import Trading212Client
        return [Trading212Client]

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_finance.agents.finance.tools",
            "ze_finance.agents.finance.agent",
        ]

    def agent_deps(self, accumulated: dict) -> dict:
        from ze_finance.store import PortfolioStore, TransactionStore
        from ze_finance.recurring.store import RecurringStore
        return {
            PortfolioStore: self._portfolio_store,
            TransactionStore: self._transaction_store,
            RecurringStore: self._recurring_store,
        }

    def signal_sources(self) -> list:
        return [self._signal_source]

    def ingestion_extractors(self) -> list:
        return [self._ingestion_extractor]

    def data_domains(self) -> list[DataDomain]:
        async def _export_transactions(db: Any) -> list[dict]:
            rows = await db.fetch("SELECT * FROM finance_transactions")
            return [dict(r) for r in rows]

        async def _delete_transactions(db: Any) -> None:
            await db.execute("DELETE FROM finance_transactions")

        async def _export_positions(db: Any) -> list[dict]:
            rows = await db.fetch("SELECT * FROM finance_positions")
            return [dict(r) for r in rows]

        async def _delete_positions(db: Any) -> None:
            await db.execute("DELETE FROM finance_positions")

        async def _export_csv_mappings(db: Any) -> list[dict]:
            rows = await db.fetch("SELECT * FROM finance_csv_mappings")
            return [dict(r) for r in rows]

        async def _delete_csv_mappings(db: Any) -> None:
            await db.execute("DELETE FROM finance_csv_mappings")

        async def _export_accounts(db: Any) -> list[dict]:
            rows = await db.fetch("SELECT * FROM finance_accounts")
            return [dict(r) for r in rows]

        async def _delete_accounts(db: Any) -> None:
            await db.execute("DELETE FROM finance_accounts")

        async def _export_recurring(db: Any) -> list[dict]:
            rows = await db.fetch("SELECT * FROM finance_recurring")
            return [dict(r) for r in rows]

        async def _delete_recurring(db: Any) -> None:
            # Delete staleness bookkeeping first (no FK, but logically coupled).
            await db.execute("DELETE FROM finance_recurring_staleness")
            await db.execute("DELETE FROM finance_recurring")

        return [
            DataDomain(
                name="finance.transactions",
                export=_export_transactions,
                delete=_delete_transactions,
                delete_order=10,
            ),
            DataDomain(
                name="finance.positions",
                export=_export_positions,
                delete=_delete_positions,
                delete_order=10,
            ),
            DataDomain(
                name="finance.csv_mappings",
                export=_export_csv_mappings,
                delete=_delete_csv_mappings,
                delete_order=10,
            ),
            DataDomain(
                name="finance.recurring",
                export=_export_recurring,
                delete=_delete_recurring,
                delete_order=10,
            ),
            DataDomain(
                name="finance.accounts",
                export=_export_accounts,
                delete=_delete_accounts,
                delete_order=20,
            ),
        ]

    async def startup(self, container: Any) -> None:
        container.proactive_scheduler.register(
            self._snapshot_job, cron=self._snapshot_cron
        )
        log.info("finance_snapshot_scheduled", cron=self._snapshot_cron)
        if self._recurring_enabled:
            container.proactive_scheduler.register(
                self._recurring_job, cron=self._recurring_cron
            )
            log.info("finance_recurring_detection_scheduled", cron=self._recurring_cron)
        else:
            log.info("finance_recurring_detection_disabled")
