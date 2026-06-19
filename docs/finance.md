# Ze Finance

Ze-finance gives Ze awareness of the user's financial life: investment positions,
bank transactions, portfolio performance, and spending patterns. This document covers
the operational specifics of the plugin — data sources, privacy model, configuration,
and the path toward a full risk engine.

---

## Table of Contents

1. [Data Sources](#data-sources)
2. [Privacy & Data Protection](#privacy--data-protection)
3. [CSV Import](#csv-import)
4. [Spending Categories](#spending-categories)
5. [Signals & Proactive Alerts](#signals--proactive-alerts)
6. [Data Deletion & Export](#data-deletion--export)
7. [Configuration Reference](#configuration-reference)
8. [Future: Risk Engine (ze-risk)](#future-risk-engine-ze-risk)

---

## Data Sources

Ze-finance ingests financial data through the `DataSource` protocol. Each source is
identified by a stable `source_id` string used for deduplication and column mapping.

### Trading212

Requires a Trading212 API key with **portfolio scope**. Set in `.env`:

```bash
TRADING212_API_KEY=your-key
TRADING212_DEMO=false   # set true to use the demo environment
```

The `Trading212DataSource` wraps `ze_trading212.Trading212Client` and maps the
raw API responses to Ze's domain types (`Position`, `Transaction`, `Account`).
It is wired automatically via the Phase 63 integration framework — no manual
changes to `container.py` are needed.

Data fetched on each sync:
- Account info and cash balance (`/equity/account/info`, `/equity/account/cash`)
- Open positions (`/equity/portfolio`)
- Order and dividend history since the last known `settled_at`

Source ID: `trading212`

### CSV (Bank Statements)

Any bank that exports CSV statements is supported. Place the export file in the
directory configured as `finance.csv_import_dir` (default: `data/finance/imports/`).

Ze detects the file's `source_id` from the filename prefix (e.g.
`revolut_2026-06.csv` → `source_id: csv:revolut`). On first import from a new
source, Ze infers the column mapping via LLM (see [CSV Import](#csv-import)).
Subsequent imports from the same source reuse the cached mapping.

**Supported formats:** UTF-8 or UTF-8-BOM, comma or semicolon delimited.
Single amount column (positive/negative) or separate debit/credit columns are
both handled.

---

## Privacy & Data Protection

Financial data is the most sensitive data Ze handles. The plugin enforces two
protection layers that cannot be overridden by global configuration.

### LLM provider pinning

All LLM calls in `ze-finance` are pinned to **Anthropic** via OpenRouter,
regardless of the global model setting in `config.yaml`. This applies to:

- `FinanceAgent` — the conversational interface
- `CsvSchemaInferrer` — column mapping inference on first import
- `CategoryInferrer` (when `finance.llm_categorization: true`) — transaction
  description classification

Anthropic's API does not train on user data submitted via the API. No financial
data is ever routed to another provider.

### Data minimisation

Raw financial rows are never placed in LLM context. Tools aggregate data locally
in Python and expose only summaries to the model.

| What the LLM sees | What stays in the DB |
|---|---|
| Total notional, total P&L, account count | Individual position quantities and prices |
| Spending totals per category | Individual transaction amounts and descriptions |
| Account cash balance | Transaction history |
| A list of positions (only when explicitly requested) | CSV mapping parameters |

The categorisation pass (see below) is the only place description strings reach
the LLM — and only when the user has opted in. Amounts, dates, and account
identifiers are never included in that call.

---

## CSV Import

### Column mapping inference

Bank CSV exports are not standardised. Ze handles this by inferring the column
mapping on the first import from each bank source.

**How it works:**

1. Ze reads the CSV header row and 5 sample rows (no real transaction data —
   just the structural shape of the file).
2. These are sent to Anthropic haiku with a prompt asking for a JSON column
   mapping: `{ date_column, amount_column, description_column, date_format, ... }`.
3. The mapping is stored in `finance_csv_mappings` keyed by `source_id`.
4. All subsequent imports from the same source apply the cached mapping in Python —
   no further LLM call.

**What is sent to the LLM during inference:**

```
Headers: Date, Description, Amount (EUR), Balance
Row 1:   2026-06-01, ALDI LISBON, -34.20, 1204.50
Row 2:   2026-06-02, UBER *TRIP, -12.40, 1192.10
Row 3:   2026-06-03, SALARY, +2800.00, 3992.10
```

Only structural data. No account number, IBAN, name, or personal identifiers.

**To reset a cached mapping** (e.g. if your bank changed its export format):

```bash
# via ze-api REST (requires API key)
DELETE /api/finance/csv-mappings/{source_id}
```

### Date formats

Ze attempts to auto-detect common date formats from the sample rows:
`%Y-%m-%d`, `%d/%m/%Y`, `%d-%m-%Y`, `%m/%d/%Y`, `%d.%m.%Y`. If
detection fails, set `finance.csv_date_format` in `config.yaml` to override.

### Deduplication

Transactions are deduplicated by `(account_id, external_id)`. For CSV sources,
`external_id` is a stable hash of `(date, amount, description)`. Re-importing
the same CSV file is safe — already-present rows are skipped.

---

## Spending Categories

Transactions are assigned a spending category at ingestion time (not at query
time). The category is stored in `finance_transactions.category` alongside a
`category_source` field (`keyword` or `llm`).

### Keyword rules (always on)

Ze first checks the transaction description against a built-in keyword ruleset:

| Category | Example keywords |
|---|---|
| Food & Dining | aldi, lidl, continente, uber eats, deliveroo, mcdonald |
| Transport | uber, bolt, cp comboios, metro, ryanair, tap air, shell, bp |
| Utilities | edp, nos, meo, vodafone, epal |
| Health | farmacia, pharmacy, clinica, hospital |
| Entertainment | netflix, spotify, steam, playstation, disney |
| Shopping | amazon, zara, h&m, fnac, worten |
| Finance | wise, revolut, trading 212, fee, commission, interest |

Matching is case-insensitive substring matching. The first matching rule wins.
Transactions that match no rule are assigned `category: "Other"`.

### LLM categorisation (opt-in)

When `finance.llm_categorization: true` is set, transactions classified as
"Other" by the keyword pass are batched and sent to Anthropic haiku for
classification.

**What is sent:**

```json
["BOOKING.COM*12345678", "DECATHLON ALMADA", "FARMACIA SAUDE LDA"]
```

Only the description string. No amounts, dates, account IDs, or balances.

**When it runs:** during the daily snapshot job, after new transactions are
appended. Categories are persisted immediately — subsequent `get_spending_summary`
calls are pure DB reads with no LLM involvement.

To enable:

```yaml
# config/config.yaml
finance:
  llm_categorization: true
```

---

## Signals & Proactive Alerts

`FinanceSignalSource` emits signals into Ze's signal substrate after each daily
snapshot. These surface as proactive notifications via the usual Ze delivery
channel (WebSocket if connected, ntfy push otherwise).

| Signal | Trigger | Severity |
|---|---|---|
| `finance.pnl_swing` | Total unrealised P&L changed > 5% vs previous snapshot | medium |
| `finance.large_transaction` | Single transaction ≥ threshold in its native currency | low |

### Large transaction threshold

The threshold (`finance.large_transaction_threshold`, default `500`) is compared
against the transaction's native currency value with **no FX conversion**. A
€600 payment and a $600 payment both trigger the signal at a threshold of `500`.

This is intentional: the threshold is nominal, not FX-adjusted. It requires no
FX rate data at signal-emission time and is predictable. The signal payload
includes the currency explicitly so the notification reads "€620 at Booking.com"
rather than an FX-normalised figure.

Currency-normalised thresholds will follow when multi-currency support is
introduced.

---

## Data Deletion & Export

`FinancePlugin` implements `data_domains()` (Phase 62) so all finance data
participates in Ze's standard export and deletion flows.

### Tables covered

| Domain | Table | delete_order |
|---|---|---|
| `finance.transactions` | `finance_transactions` | 10 |
| `finance.positions` | `finance_positions` | 10 |
| `finance.csv_mappings` | `finance_csv_mappings` | 10 |
| `finance.accounts` | `finance_accounts` | 20 |

Accounts are deleted last because positions and transactions reference them via
foreign key. Import follows the reverse order (accounts first, then children).

### Export

A full export via `GET /api/data/export` includes:

```
finance.accounts.json       — account metadata and balances
finance.positions.json      — current position snapshot
finance.transactions.json   — full transaction ledger
finance.csv_mappings.json   — cached column mappings per bank source
```

### Deletion

`DELETE /api/data` (with typed-phrase confirmation) wipes all four tables. This
is a hard delete with no recovery path. Export your data first.

---

## Configuration Reference

### `.env`

| Variable | Description |
|---|---|
| `TRADING212_API_KEY` | Trading212 REST API key (portfolio scope required) |
| `TRADING212_DEMO` | `true` to use the demo environment (default: `false`) |

### `config/config.yaml`

```yaml
finance:
  snapshot_schedule: "0 8 * * *"   # cron — when the daily snapshot job runs
  large_transaction_threshold: 500  # nominal threshold; compared in native currency
  llm_categorization: false         # opt-in LLM batch categorisation (Anthropic only)
```

---

## Future: Risk Engine (ze-risk)

Ze-finance is designed as the substrate for a full factor-based risk engine,
inspired by [RiskOS](https://github.com/joaoajmatos/riskos). The risk layer
is a separate plugin (`ze-risk`) that imports from `ze_finance.risk.types`.

### Factor taxonomy

Ze-finance already defines the full factor taxonomy as a stub in
`ze_finance.risk.types.FactorTaxonomy`. Twelve factors across three tiers:

**Primary** (drive drift alerts on their own):
`AI_SENTIMENT`, `RISK_APPETITE`, `CRYPTO_MOMENTUM`, `SEMICONDUCTOR_CYCLE`, `EM_STRESS`

**Amplifiers** (tighten thresholds when elevated):
`LIQUIDITY_STRESS`, `DOLLAR_STRENGTH`, `VOLATILITY_REGIME`, `GEOPOLITICAL_TENSION`

**Structural** (slower-moving regime indicators):
`RATE_REGIME`, `TECH_REGULATION`, `CHINA_RISK`, `MIDDLE_EAST_RISK`

### What ze-risk will add

- **Factor exposure mapping** — OLS regression to map each position's returns
  to the factor taxonomy. Manual override via `exposures.json` for assets with
  insufficient history.
- **Silent drift detection** — alert when portfolio concentration on a single
  factor (e.g. AI_SENTIMENT) exceeds a configured threshold, without waiting for
  a market event.
- **Scenario modelling** — stress-test the portfolio against historical presets
  (2022 rate shock, AI correction, crypto deleveraging, geopolitical escalation,
  etc.) and custom factor shocks.
- **LP-optimised rebalancing** — suggest cash-neutral trades that minimise
  modelled scenario loss, subject to turnover and concentration constraints.
- **Signal ingestion** — yfinance (prices), FRED (macro), CoinGecko (crypto),
  RSS headlines, and geopolitical feeds (GDELT, ACLED) as factor signal sources.

### Notional field

`Position.notional` is the aggregation unit for the risk engine. It is
always populated at ingestion time (quantity × current price). The risk engine
never aggregates on quantity — shares, crypto units, and cash are not comparable
across asset classes. If you extend the DataSource protocol with a new broker,
always populate `notional`.
