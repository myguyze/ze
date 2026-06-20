# ze-finance

Finance domain plugin for Ze — portfolio positions, bank transactions, spending summaries, and proactive P&L alerts.

## Role in Ze

Ze-finance gives Ze awareness of the user's financial life. It ingests investment data from Trading212 and bank transactions from CSV statements, stores them in normalised Postgres tables, and exposes them through the `FinanceAgent` and a daily snapshot job. All LLM calls in this plugin are pinned to Anthropic via OpenRouter — financial data never reaches another provider.

The plugin is designed as the substrate for a full factor-based risk engine (`ze-risk`, future). The domain types and protocol stubs are already defined under `risk/` and `models/` so the risk layer can import from `ze_finance.*` without restructuring.

### Key features

- `FinanceAgent` — conversational interface for portfolio, spending, and recurring expense questions
- Trading212 integration — positions, P&L, order and dividend history
- CSV bank statement import with LLM-assisted column mapping inference (cached per source)
- Two-tier spending categorisation: keyword rules first, optional Anthropic haiku batch for unmatched descriptions
- Recurring expense detection — algorithmic detection of subscriptions and fixed charges at any cadence (weekly, biweekly, monthly, quarterly, …); opt-in, with confirm/dismiss UX and price-change resurface
- Daily snapshot job — syncs all data sources, updates categories, emits signals
- Monthly recurring detection job — detects new recurring charges, nudges on stale CSV data
- `FinanceSignalSource` — P&L swing and large transaction signals into the Ze signal substrate
- Anthropic-pinned LLM calls — financial data never leaves the Anthropic provider

### Integration

Entry point `ze_finance`. Contributes `FinanceAgent`, `DailySnapshotJob`, `RecurringDetectionJob`, and `FinanceSignalSource`. Migrations under `zfin` branch.

```python
from ze_finance.plugin import FinancePlugin
```

## Responsibilities

| Module | What it provides |
|---|---|
| `agents/finance/` | `FinanceAgent` and its `@tool` functions (`get_portfolio_summary`, `get_positions`, `get_spending_summary`, `get_recent_transactions`, `get_account_balances`, `get_recurring_expenses`, `confirm_recurring`, `dismiss_recurring`) |
| `categoriser.py` | `CategoryInferrer` — keyword rules + optional Anthropic haiku batch for "Other" descriptions |
| `errors.py` | `FinanceError`, `ZeIntegrationError`, `FinanceParseError` |
| `jobs/snapshot.py` | `DailySnapshotJob` — syncs all data sources, runs categorisation, emits signals |
| `jobs/recurring.py` | `RecurringDetectionJob` — monthly job; detects new recurring charges, handles CSV staleness nudges |
| `models/alpha.py` | `AlphaModel` Protocol stub (future `ze-risk` extension point) |
| `plugin.py` | `FinancePlugin(ZePlugin)` — registers agent, jobs, signal source, and data domains |
| `recurring/types.py` | `RecurringExpense`, `RecurringStatus`, `UpsertResult`; `snap_interval()`, `cadence_label()` |
| `recurring/detector.py` | `RecurringDetector` — pure, stateless gap-analysis algorithm |
| `recurring/store.py` | `RecurringStore` — upsert with price-change resurface logic, confirm/dismiss, nudge rate-limiting |
| `risk/types.py` | `FactorTaxonomy` enum — 12-factor taxonomy for the future risk engine |
| `risk/engine.py` | `RiskEngine` Protocol stub |
| `signals/finance.py` | `FinanceSignalSource` — emits `finance.pnl_swing` and `finance.large_transaction` signals |
| `source.py` | `DataSource` Protocol — implemented by all ingestion backends |
| `sources/trading212.py` | `Trading212DataSource` — maps Trading212 REST API responses to Ze domain types |
| `sources/csv.py` | `CsvDataSource` + `CsvSchemaInferrer` — parses bank CSV exports, infers column mapping via LLM on first import |
| `store.py` | `PortfolioStore`, `TransactionStore`, `CsvMappingStore` — Postgres-backed storage |
| `types.py` | Domain types: `Asset`, `Account`, `Position`, `Transaction`, `SpendingSummary`, `CsvMapping` |

## Dependencies

```mermaid
graph LR
    finance[ze-finance] --> sdk[ze-sdk]
    finance --> trading212[ze-trading212]
```

## Configuration

### `.env`

| Variable | Description |
|---|---|
| `TRADING212_API_KEY` | Trading212 REST API key (portfolio scope required) |
| `TRADING212_DEMO` | `true` to use the demo environment (default: `false`) |

### `config/config.yaml`

```yaml
finance:
  snapshot_schedule: "0 8 * * *"         # cron for the daily snapshot job
  large_transaction_threshold: 500        # nominal threshold (native currency, no FX conversion)
  llm_categorization: false               # opt-in LLM batch categorisation (Anthropic only)

  # Recurring expense detection — off by default
  recurring_detection_enabled: false          # set true to enable the monthly detection job
  recurring_detection_schedule: "0 9 1 * *"  # 1st of each month at 09:00
  recurring_staleness_days: 35                # CSV accounts older than this get a nudge
  recurring_nudge_cooldown_days: 14           # minimum days between nudges per account
  recurring_price_change_threshold: 0.10      # resurface dismissed items if amount changes >10%
  recurring_lookback_days: 90                 # transaction history window for detection
```

## Testing

From the repo root:

```bash
make test-finance
```

See [docs/testing.md](../../docs/testing.md).
