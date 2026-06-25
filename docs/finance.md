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
5. [Recurring Expense Detection](#recurring-expense-detection)
6. [Signals & Proactive Alerts](#signals--proactive-alerts)
7. [Data Deletion & Export](#data-deletion--export)
8. [Configuration Reference](#configuration-reference)
9. [Future: Risk Engine (ze-risk)](#future-risk-engine-ze-risk)

> **Ingestion shortcut:** upload or share a bank statement PDF/CSV directly with Ze
> and `FinanceIngestionExtractor` will write structured transactions to the finance
> store automatically. See [Data Sources → Ingestion pipeline](#ingestion-pipeline-pdf-and-csv-via-chat).

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

### Ingestion pipeline (PDF and CSV via chat)

CSV files and PDF bank statements can also be submitted directly through Ze's
ingestion pipeline — paste a URL, upload a file, or tell Ze to "learn from this statement."

`FinanceIngestionExtractor` intercepts content classified as `pdf`, `plain_text`, or
`document` during the ingestion pipeline and writes structured `Transaction` rows
directly into `finance_transactions`, bypassing the fact-strings-only path used by
the default `LLMExtractor`.

- **PDF statements** — LLM parses the processed text and returns a JSON array of transactions.
- **CSV statements** — `CsvSchemaInferrer` detects column layout (cached per source after the first run), then `CsvDataSource` parses rows into `Transaction` objects.

In both cases the transactions land in the same `finance_transactions` table as
Trading212 and batch CSV imports — fully queryable, categorisable, and covered by
the `finance.transactions` DataDomain for export and deletion.

A summary and per-transaction facts are also pushed to `ze-memory`, so Ze can
reference them conversationally without touching raw financial rows.

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

## Recurring Expense Detection

Ze can automatically surface subscriptions, rent, utility bills, and other fixed
charges from transaction history — without the user having to categorise them
manually.

### Opt-in

Recurring detection is **off by default**. Enable it by telling Ze:

> "Track my recurring expenses" / "Show me my subscriptions"

Ze enables the `finance.recurring_detection` capability, runs a one-shot detection
pass over the last 90 days of transactions, and notifies you of candidates found.

### How detection works

Detection is purely algorithmic — no LLM involved, no description text sent
anywhere. The steps:

1. Filter to spending transactions (`withdrawal`, `fee`).
2. Normalise the description: lowercase, strip digits and punctuation, collapse
   whitespace. This groups `"Netflix 1234"` and `"Netflix 5678"` under the same key.
   When `finance.nli_merchant_merge_enabled: true`, alias descriptions within the
   same account and currency (e.g. `NETFLIX.COM` / `Netflix`) are merged via embedding
   cosine prefilter + NLI entailment before grouping.
3. Group by `(normalised description, currency, account)`.
4. For each group, compute the gaps in days between consecutive occurrences.
5. Reject the group if any gap falls outside ±40% of the median gap — this filters
   erratic patterns (e.g. charges that appear weekly some months and monthly others).
6. Snap the median gap to the nearest natural billing interval:
   `1, 7, 14, 21, 28, 30, 42, 60, 90, 120, 180, 365` days.
7. Require total span ≥ max(1.5 × interval, 14 days). Two purchases a few days apart
   do not qualify as recurring.
8. Reject if the coefficient of variation of amounts exceeds 10% — variable-amount
   charges (food delivery, irregular bills) are not flagged as subscriptions.

### Supported cadences

Ze detects any billing cycle that maps to a natural interval — not just monthly:

| Interval | Label |
|---|---|
| 7 days | weekly |
| 14 days | every 2 weeks |
| 21 days | every 3 weeks |
| 28 days | every 4 weeks |
| 30 days | monthly |
| 42 days | every 6 weeks |
| 60 days | every 2 months |
| 90 days | quarterly |
| 180 days | every 6 months |
| 365 days | yearly |

> **Note:** annual charges (365-day cycle) require at least 2 occurrences spanning
> more than 1.5 years, so a 90-day lookback window will not detect them. The lookback
> window can be extended via `finance.recurring_lookback_days`.

### Candidate lifecycle

Detected candidates have three states:

| Status | Meaning |
|---|---|
| `detected` | Found by Ze, not yet reviewed by the user |
| `confirmed` | User said "yes, track this" |
| `dismissed` | User said "ignore this" |

When new candidates are found, Ze sends a push notification listing them. Opening
the chat presents a `render_confirm` card per item:

> *"Is this a subscription you want to track?"*  
> Netflix — EUR 15.99/monthly  **[Yes, track it]** **[Ignore]**

Tapping a button calls `confirm_recurring` or `dismiss_recurring` respectively.

### Price-change resurface

A dismissed charge is normally permanent. However, if the detected amount changes
by more than `finance.recurring_price_change_threshold` (default 10%), Ze resets
the status to `detected` and sends a targeted notification:

> "Your Netflix charge changed from EUR 15.99 to EUR 17.99 — still happy with it?"

Below the threshold, dismissed stays dismissed.

### Data freshness and CSV nudges

The `RecurringDetectionJob` runs on the 1st of each month at 09:00 (configurable).
Before running detection on an account, it checks the age of the most recent
transaction:

- **CSV-sourced accounts** (`source_id` starts with `csv:`): if no new transactions
  have been seen for more than `finance.recurring_staleness_days` (default 35) days,
  Ze skips detection and sends a push nudge:

  > "I haven't seen new transactions for 'Revolut' in 40 days. Upload a fresh bank
  > statement so I can keep your recurring expense list up to date."

  Nudges are rate-limited to once per account per `finance.recurring_nudge_cooldown_days`
  (default 14) days.

- **Live-connected accounts** (Trading212): staleness means the daily snapshot job
  failed. Ze logs an error but does not nudge — there's nothing the user can do.

### Asking Ze about recurring expenses

Ze can answer recurring-expense questions conversationally at any time (not just
after the job runs):

> "What subscriptions do I have?"  
> "What are my monthly fixed costs?"  
> "Show me all the recurring charges you've detected"

The `FinanceAgent` calls `get_recurring_expenses` and can filter by status
(`detected`, `confirmed`, or `dismissed`).

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

| Domain | Tables | delete_order |
|---|---|---|
| `finance.transactions` | `finance_transactions` | 10 |
| `finance.positions` | `finance_positions` | 10 |
| `finance.csv_mappings` | `finance_csv_mappings` | 10 |
| `finance.recurring` | `finance_recurring`, `finance_recurring_staleness` | 10 |
| `finance.accounts` | `finance_accounts` | 20 |

Accounts are deleted last because positions and transactions reference them via
foreign key. `finance_recurring_staleness` (nudge timestamps) is deleted together
with `finance_recurring` — it is internal bookkeeping and is not exported
separately.

### Export

A full export via `GET /api/data/export` includes:

```
finance.accounts.json       — account metadata and balances
finance.positions.json      — current position snapshot
finance.transactions.json   — full transaction ledger
finance.csv_mappings.json   — cached column mappings per bank source
finance.recurring.json      — detected/confirmed/dismissed recurring charges
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
  snapshot_schedule: "0 8 * * *"         # cron — when the daily snapshot job runs
  large_transaction_threshold: 500        # nominal threshold; compared in native currency
  llm_categorization: false               # opt-in LLM batch categorisation (Anthropic only)

  # Recurring expense detection (Phase 70) — off by default
  recurring_detection_enabled: false          # set true to enable the monthly detection job
  recurring_detection_schedule: "0 9 1 * *"  # 1st of each month at 09:00
  recurring_staleness_days: 35                # CSV accounts older than this get a nudge
  recurring_nudge_cooldown_days: 14           # minimum days between nudges per account
  recurring_price_change_threshold: 0.10      # resurface dismissed items if amount changes >10%
  recurring_lookback_days: 90                 # transaction history window for detection

  nli_merchant_merge_enabled: false           # merge merchant aliases via NLI before grouping
  nli_merchant_cosine_threshold: 0.70
  nli_merchant_entailment_threshold: 0.70
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
