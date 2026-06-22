# Finance Plugin — Spec

> **Package:** `ze-finance` (`plugins/ze-finance/`)
> **Phase:** 67
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| Core types (`types.py`) | ✅ Done |
| `DataSource` protocol | ✅ Done |
| `Trading212DataSource` | ✅ Done |
| `CsvDataSource` + `CsvSchemaInferrer` | ✅ Done |
| `PortfolioStore` / `TransactionStore` | ✅ Done |
| `CategoryInferrer` (keyword rules + opt-in LLM) | ✅ Done |
| `FinanceAgent` + tools (data-minimised) | ✅ Done |
| `FinanceSignalSource` | ✅ Done |
| Daily snapshot job | ✅ Done |
| `risk/` stubs | ✅ Done |
| `models/` stubs | ✅ Done |
| `FinancePlugin` (incl. `data_domains()`) | ✅ Done |
| Migrations | ✅ Done |
| Tests | ✅ Done |

---

## Purpose

Ze-finance gives Ze awareness of the user's financial life: investment positions,
bank transactions, portfolio performance, and spending patterns. The FinanceAgent
answers conversational questions ("how is my T212 portfolio today?", "what did I
spend on food this month?") and proactively surfaces notable events (large
transactions, significant P&L swings).

This phase builds the substrate: domain types, data ingestion (Trading212 + CSV),
storage, and the FinanceAgent. It also lays the architectural foundations — protocol
stubs for a factor-based risk engine and alpha models — so that a full RiskOS-style
risk layer (`ze-risk`) can be introduced later without restructuring the domain.

---

## Responsibilities

- Define the canonical financial domain types used by all downstream risk and
  modelling layers.
- Ingest positions and transactions from Trading212 (via `ze_trading212`) and from
  bank CSV exports.
- Infer CSV column mappings via LLM on first import and cache them per source.
- Persist portfolio snapshots and transaction history in Postgres.
- Expose a `FinanceAgent` that answers portfolio and spending questions
  conversationally, using pre-aggregated tool outputs to minimise LLM data exposure.
- Route all LLM calls to Anthropic via OpenRouter for data protection.
- Emit `FinanceSignalSource` signals (P&L swing, large transaction) into Ze's signal
  substrate for proactive delivery.
- Participate in the data deletion and export system via `data_domains()`.
- Define `RiskEngine`, `FactorTaxonomy`, and `AlphaModel` as Protocol stubs so
  `ze-risk` has a stable import contract.

---

## Out of Scope

- Factor exposure computation, OLS regression, drift detection — deferred to `ze-risk`.
- Scenario modelling, LP-optimised rebalancing — deferred to `ze-risk`.
- Options / derivatives position support — deferred; `AssetClass.OPTION` is in the
  enum but no tools or store logic handle it in this phase.
- Open Banking / PSD2 integration — planned; `DataSource` protocol accommodates it.
- Live price streaming or intraday data — positions are refreshed on demand or on
  schedule, not streamed.
- Multi-currency conversion — all notionals stored in the position currency;
  conversion to a base currency is deferred.
- Tax lot accounting and capital gains calculation.

---

## Module Location

```
integrations/
  ze-trading212/              # already exists — no changes this phase

plugins/
  ze-finance/
    pyproject.toml
    ze_finance/
      __init__.py
      types.py                # core domain types
      source.py               # DataSource protocol
      sources/
        __init__.py
        trading212.py         # Trading212DataSource
        csv.py                # CsvDataSource + CsvSchemaInferrer
      store.py                # PortfolioStore, TransactionStore, CsvMappingStore
      categoriser.py          # CategoryInferrer (keyword rules + opt-in LLM batch)
      signals/
        __init__.py
        finance.py            # FinanceSignalSource
      agents/
        finance/
          __init__.py
          agent.py            # FinanceAgent
          tools.py            # @tool definitions (data-minimised)
      jobs/
        __init__.py
        snapshot.py           # DailySnapshotJob
      risk/
        __init__.py
        engine.py             # RiskEngine Protocol (stub)
        types.py              # FactorTaxonomy, FactorExposure, FactorReading (stubs)
      models/
        __init__.py
        alpha.py              # AlphaModel Protocol (stub)
      plugin.py               # FinancePlugin(ZePlugin)
      migrations/
        env.py
        script.py.mako
        versions/
          zfin001_finance_tables.py
```

---

## Data Protection

Financial data is among the most sensitive personal data Ze handles. Two
principles apply to this plugin:

### Anthropic-only LLM routing

All LLM calls originating from `ze-finance` are pinned to Anthropic via
OpenRouter. Anthropic's API does not train on user data. This is enforced
at the agent level via `model = "anthropic/claude-haiku-4-5-20251001"`.
The `CsvSchemaInferrer` uses the same provider.

No finance data ever reaches a non-Anthropic model, regardless of the
global model configuration in `config.yaml`.

### Data minimisation

Raw financial rows are never placed in LLM context. Tools aggregate locally
in Python and send only summaries to the model. The principle: **if the LLM
doesn't need it, it doesn't see it**.

Concretely:
- `get_portfolio_summary` returns total notional, total unrealised P&L, and
  per-account breakdown — not individual positions unless the user explicitly
  asks for them.
- `get_positions` returns positions as a structured list only when the user's
  question requires it (e.g. "which positions are down today?").
- `get_transactions` returns aggregated spending by category and period by
  default. The raw list is returned only when the user asks for individual
  transactions by name or date.
- `get_account_balance` returns a single number.

See the Tools section for exact output shapes.

---

## Interface Contract

### DataSource protocol

```python
# ze_finance/source.py
from __future__ import annotations
from datetime import datetime
from typing import Protocol
from .types import Account, Position, Transaction

class DataSource(Protocol):
    @property
    def source_id(self) -> str:
        """Stable identifier for this source (e.g. 'trading212', 'csv:revolut')."""
        ...

    async def fetch_account(self) -> Account: ...
    async def fetch_positions(self) -> list[Position]: ...
    async def fetch_transactions(self, since: datetime) -> list[Transaction]: ...
```

### PortfolioStore

```python
class PortfolioStore:
    async def upsert_account(self, account: Account) -> None: ...
    async def upsert_positions(self, positions: list[Position]) -> None: ...
    async def get_positions(self, account_id: str | None = None) -> list[Position]: ...
    async def get_account(self, account_id: str) -> Account | None: ...
    async def list_accounts(self) -> list[Account]: ...

class TransactionStore:
    async def append(self, transactions: list[Transaction]) -> int:
        """Insert transactions not already present; return count inserted."""
        ...
    async def get(
        self,
        account_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 200,
    ) -> list[Transaction]: ...
    async def spending_by_category(
        self,
        since: datetime,
        until: datetime,
        account_id: str | None = None,
    ) -> list[SpendingSummary]: ...

class CsvMappingStore:
    async def get(self, source_id: str) -> CsvMapping | None: ...
    async def upsert(self, source_id: str, mapping: CsvMapping) -> None: ...
    async def delete(self, source_id: str) -> None: ...
```

### Errors

| Condition | Behaviour |
|-----------|-----------|
| Trading212 API key absent | `DataSource` not instantiated; agent replies "Trading212 not configured." |
| Trading212 API returns 4xx/5xx | Raises `ZeIntegrationError`; agent catches and reports. |
| CSV column mapping mismatch | Raises `FinanceParseError` with the offending row number. |
| CSV schema inference fails | Raises `FinanceParseError("Could not infer column mapping")`. |
| Account not found | `get_account` returns `None`; callers treat as missing. |

---

## Data Structures

```python
# ze_finance/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum


class AssetClass(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO = "crypto"
    BOND = "bond"
    CASH = "cash"
    OPTION = "option"   # reserved; not handled in Phase 67


class AccountType(str, Enum):
    BROKERAGE = "brokerage"
    BANK = "bank"
    CRYPTO = "crypto"
    ISA = "isa"


class TransactionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"


@dataclass(frozen=True)
class Asset:
    ticker: str                    # exchange ticker or CoinGecko ID
    name: str
    asset_class: AssetClass
    currency: str                  # ISO 4217


@dataclass
class Account:
    id: str                        # stable source-scoped identifier
    source_id: str                 # e.g. "trading212", "csv:revolut"
    account_type: AccountType
    name: str
    currency: str
    balance: Decimal
    updated_at: datetime


@dataclass
class Position:
    account_id: str
    asset: Asset
    quantity: Decimal
    # notional is the authoritative aggregation unit — always store this.
    # For Phase 67 it equals quantity × current_price. The risk engine will
    # use this field directly; never aggregate on quantity.
    notional: Decimal              # in position currency
    average_price: Decimal
    current_price: Decimal
    unrealised_pnl: Decimal
    currency: str
    updated_at: datetime


@dataclass
class Transaction:
    id: str                        # source-scoped stable ID (used for dedup)
    account_id: str
    transaction_type: TransactionType
    asset: Asset | None            # None for deposits / withdrawals
    quantity: Decimal
    price: Decimal
    fees: Decimal
    currency: str
    settled_at: datetime
    notes: str = ""


@dataclass
class SpendingSummary:
    """Aggregated output for data-minimised tool responses."""
    category: str                  # inferred from transaction notes
    total: Decimal
    currency: str
    transaction_count: int


@dataclass
class CsvMapping:
    """Persisted column mapping for a specific bank CSV format."""
    source_id: str
    date_column: str
    amount_column: str
    description_column: str
    date_format: str               # e.g. "%Y-%m-%d", "%d/%m/%Y"
    debit_column: str | None = None   # if bank uses separate debit/credit columns
    credit_column: str | None = None
    currency_column: str | None = None
    inferred_at: datetime = field(default_factory=datetime.utcnow)
```

### Category Inferrer

```python
# ze_finance/categoriser.py

# Built-in keyword ruleset. Checked before any LLM call.
_KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("Food & Dining",   ["uber eats", "deliveroo", "bolt food", "glovo", "continente",
                         "pingo doce", "lidl", "aldi", "mercadona", "mcdonald",
                         "starbucks", "nando", "pizza"]),
    ("Transport",       ["uber", "bolt", "cp comboios", "metro", "carris", "ryanair",
                         "tap air", "easyjet", "renfe", "shell", "bp ", "galp"]),
    ("Utilities",       ["edp ", "galp energia", "nos ", "meo ", "vodafone", "epal",
                         "internet", "electricity", "gas "]),
    ("Health",          ["farmacia", "pharmacy", "clinica", "hospital", "dr ", "dra "]),
    ("Entertainment",   ["netflix", "spotify", "steam", "playstation", "xbox",
                         "youtube", "prime video", "hbo", "disney"]),
    ("Shopping",        ["amazon", "zara", "h&m", "fnac", "worten", "leroy merlin"]),
    ("Finance",         ["transferwise", "wise", "revolut", "trading 212", "degiro",
                         "fee", "commission", "interest"]),
]


class CategoryInferrer:
    """
    Assigns a spending category to each transaction.

    Always runs the keyword ruleset first (free, no data exposure).
    If `llm_enabled=True`, transactions that fall through to "Other" are batched
    and sent to Anthropic (haiku) for classification. Results are written back to
    `finance_transactions.category` so subsequent reads never re-classify.
    """

    def __init__(self, client: LLMClient | None, llm_enabled: bool) -> None:
        self._client = client
        self._llm_enabled = llm_enabled and client is not None

    def infer_keyword(self, description: str) -> str:
        """Synchronous; always available."""
        lowered = description.lower()
        for category, keywords in _KEYWORD_RULES:
            if any(kw in lowered for kw in keywords):
                return category
        return "Other"

    async def infer_batch(self, descriptions: list[str]) -> list[str]:
        """
        Classify a batch of descriptions.
        Keyword rules run first; only "Other" descriptions are forwarded to the LLM.
        Returns a list of categories in the same order as `descriptions`.
        """
        results = [self.infer_keyword(d) for d in descriptions]
        if not self._llm_enabled:
            return results

        unresolved_indices = [i for i, c in enumerate(results) if c == "Other"]
        if not unresolved_indices:
            return results

        # Only description text is sent — no amounts, accounts, or dates.
        batch = [descriptions[i] for i in unresolved_indices]
        llm_categories = await self._call_llm(batch)
        for idx, category in zip(unresolved_indices, llm_categories):
            results[idx] = category
        return results

    async def _call_llm(self, descriptions: list[str]) -> list[str]:
        # Sends only the merchant/description strings.
        # Model: anthropic/claude-haiku-4-5-20251001
        # Returns a JSON array of category strings, same length as input.
        ...
```

**Data flow when LLM categorisation is enabled:**
- Only the transaction description string (merchant name, reference) is sent.
- Amounts, dates, account identifiers, and balances are never included.
- Categories are stored in `finance_transactions.category` at ingestion time.
- Subsequent `get_spending_summary` calls read from DB — no LLM call at query time.

### CSV Schema Inferrer

```python
# ze_finance/sources/csv.py

class CsvSchemaInferrer:
    """
    Sends the CSV header + 5 sample rows to Anthropic and returns a CsvMapping.
    Called once per source_id; result is persisted and reused on subsequent imports.
    """

    def __init__(self, client: LLMClient, mapping_store: CsvMappingStore) -> None:
        self._client = client
        self._store = mapping_store

    async def infer(self, source_id: str, header: list[str], samples: list[list[str]]) -> CsvMapping:
        cached = await self._store.get(source_id)
        if cached:
            return cached
        mapping = await self._call_llm(source_id, header, samples)
        await self._store.upsert(source_id, mapping)
        return mapping

    async def _call_llm(self, source_id: str, header: list[str], samples: list[list[str]]) -> CsvMapping:
        # Sends header + samples only — no real transaction data
        ...
```

The LLM prompt includes only the CSV header and 5 sample rows (no real amounts or
personal details from actual transactions). It asks the model to return a JSON object
with the column mapping. This is the only LLM call in the CSV ingestion path.

### Risk stubs

```python
# ze_finance/risk/types.py
from enum import Enum
from dataclasses import dataclass
from decimal import Decimal


class FactorTaxonomy(str, Enum):
    # Primary — drive drift alerts on their own
    AI_SENTIMENT          = "ai_sentiment"
    RISK_APPETITE         = "risk_appetite"
    CRYPTO_MOMENTUM       = "crypto_momentum"
    SEMICONDUCTOR_CYCLE   = "semiconductor_cycle"
    EM_STRESS             = "em_stress"
    # Amplifiers — tighten thresholds when elevated
    LIQUIDITY_STRESS      = "liquidity_stress"
    DOLLAR_STRENGTH       = "dollar_strength"
    VOLATILITY_REGIME     = "volatility_regime"
    GEOPOLITICAL_TENSION  = "geopolitical_tension"
    # Structural — slower-moving, monitored for regime shifts
    RATE_REGIME           = "rate_regime"
    TECH_REGULATION       = "tech_regulation"
    CHINA_RISK            = "china_risk"
    MIDDLE_EAST_RISK      = "middle_east_risk"


@dataclass
class FactorExposure:
    """Placeholder. Phase 67 never populates this — it is the ze-risk contract."""
    factor: FactorTaxonomy
    exposure: Decimal   # portfolio-level exposure weight (-1 to +1)
    notional: Decimal   # USD notional driving this exposure


@dataclass
class FactorReading:
    """A single time-series observation of a factor's value."""
    factor: FactorTaxonomy
    value: float        # normalised z-score or raw reading depending on factor
    source: str
    observed_at: "datetime"
```

```python
# ze_finance/risk/engine.py
from typing import Protocol
from .types import FactorExposure
from ..types import Position


class RiskEngine(Protocol):
    """ze-risk will provide a concrete implementation; ze-finance never instantiates one."""

    async def compute_exposures(self, positions: list[Position]) -> list[FactorExposure]: ...
    async def check_drift(self, exposures: list[FactorExposure]) -> list[str]: ...
```

```python
# ze_finance/models/alpha.py
from typing import Protocol
from ..types import Asset


class AlphaModel(Protocol):
    """Reserved for signal-driven strategy models in a future phase."""

    async def score(self, asset: Asset) -> float: ...
```

---

## Database Schema

Migration branch prefix: `zfin`

```sql
-- zfin001

CREATE TABLE finance_accounts (
    id              TEXT        PRIMARY KEY,
    source_id       TEXT        NOT NULL,
    account_type    TEXT        NOT NULL,
    name            TEXT        NOT NULL,
    currency        TEXT        NOT NULL,
    balance         NUMERIC     NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Current positions snapshot. Replaced on each sync — not an append-only ledger.
CREATE TABLE finance_positions (
    id              BIGSERIAL   PRIMARY KEY,
    account_id      TEXT        NOT NULL REFERENCES finance_accounts(id),
    ticker          TEXT        NOT NULL,
    asset_name      TEXT        NOT NULL,
    asset_class     TEXT        NOT NULL,
    quantity        NUMERIC     NOT NULL,
    notional        NUMERIC     NOT NULL,   -- always populated; risk engine key
    average_price   NUMERIC     NOT NULL,
    current_price   NUMERIC     NOT NULL,
    unrealised_pnl  NUMERIC     NOT NULL,
    currency        TEXT        NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, ticker)
);

-- Immutable transaction ledger. Deduped by (account_id, external_id).
CREATE TABLE finance_transactions (
    id              BIGSERIAL   PRIMARY KEY,
    external_id     TEXT        NOT NULL,
    account_id      TEXT        NOT NULL REFERENCES finance_accounts(id),
    transaction_type TEXT       NOT NULL,
    ticker          TEXT,                   -- NULL for deposits/withdrawals
    asset_name      TEXT,
    asset_class     TEXT,
    quantity        NUMERIC     NOT NULL DEFAULT 0,
    price           NUMERIC     NOT NULL DEFAULT 0,
    fees            NUMERIC     NOT NULL DEFAULT 0,
    currency        TEXT        NOT NULL,
    settled_at      TIMESTAMPTZ NOT NULL,
    notes           TEXT        NOT NULL DEFAULT '',
    -- Populated at ingestion time by CategoryInferrer (keyword rules, or LLM if enabled).
    -- NULL until the first categorisation pass runs.
    category        TEXT,
    category_source TEXT,       -- 'keyword' | 'llm'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (account_id, external_id)
);

CREATE INDEX finance_transactions_account_settled
    ON finance_transactions (account_id, settled_at DESC);

-- Cached CSV column mappings — one row per bank source.
CREATE TABLE finance_csv_mappings (
    source_id           TEXT        PRIMARY KEY,
    date_column         TEXT        NOT NULL,
    amount_column       TEXT,
    debit_column        TEXT,
    credit_column       TEXT,
    description_column  TEXT        NOT NULL,
    currency_column     TEXT,
    date_format         TEXT        NOT NULL,
    inferred_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## Configuration

```yaml
# config/config.yaml
finance:
  snapshot_schedule: "0 8 * * *"   # daily at 08:00
  large_transaction_threshold: 500  # signal threshold in account currency (nominal, not FX-adjusted)
  llm_categorization: false         # opt-in: send uncategorised transaction descriptions to Anthropic
```

```bash
# .env
TRADING212_API_KEY=your-key
TRADING212_DEMO=false
```

---

## Agent

```python
# ze_finance/agents/finance/agent.py
_AGENT_INSTRUCTIONS = """
You are Ze's finance assistant. You have access to the user's investment portfolio
and bank transaction history.

Use the available tools to answer portfolio questions accurately. Always state the
reference date of the data — positions are point-in-time snapshots, not live prices.
Never speculate about future prices or give investment advice.

For questions about factor risk, concentration, or exposure analysis, tell the user
that risk analysis will be available in a future update.
"""

@agent
class FinanceAgent(BaseAgent):
    description = "Answers questions about investment portfolio, positions, P&L, and spending"
    # Pinned to Anthropic — financial data must not reach other providers.
    model = "anthropic/claude-haiku-4-5-20251001"
    intents = [
        "portfolio", "positions", "investments", "P&L", "returns",
        "spending", "transactions", "balance", "Trading212",
        "how much", "how is my", "what did I spend",
    ]
    tools = [
        "get_portfolio_summary",
        "get_positions",
        "get_spending_summary",
        "get_transactions",
        "get_account_balance",
    ]
    timeout = 60
```

---

## Tools

All tools aggregate or filter locally before returning. Raw rows are never placed
directly in LLM context.

### `get_portfolio_summary`

Returns total notional, total unrealised P&L, and a per-account breakdown.
**Does not include individual tickers** unless `include_positions=True` is passed.

```python
# Output shape (default):
{
  "total_notional": "12450.00",
  "total_unrealised_pnl": "340.50",
  "total_unrealised_pnl_pct": "2.81",
  "accounts": [
    {
      "name": "T212 ISA",
      "notional": "12450.00",
      "unrealised_pnl": "340.50",
      "position_count": 8,
      "updated_at": "2026-06-19T08:00:00Z"
    }
  ]
}
```

### `get_positions`

Returns individual positions for a given account. Called only when the user asks
about specific holdings.

```python
# Output shape:
[
  {
    "ticker": "NVDA",
    "name": "NVIDIA Corp",
    "asset_class": "equity",
    "quantity": "10",
    "notional": "1340.00",
    "unrealised_pnl": "+120.00",
    "unrealised_pnl_pct": "+9.8"
  },
  ...
]
```

### `get_spending_summary`

Aggregates bank transactions into spending categories for a given period.
**Default tool for spending questions** — raw transaction list is not returned.

```python
# Output shape:
{
  "period": "2026-06-01 to 2026-06-19",
  "total_spent": "843.20",
  "currency": "EUR",
  "categories": [
    { "category": "Food & Dining", "total": "340.00", "count": 23 },
    { "category": "Transport",     "total": "124.50", "count": 8 },
    { "category": "Utilities",     "total": "87.00",  "count": 2 },
    { "category": "Other",         "total": "291.70", "count": 15 }
  ]
}
```

### `get_transactions`

Returns individual transactions, filtered by account, period, and type. Called only
when the user asks for specific transaction details (e.g. "show me my last 5
purchases"). Capped at 50 rows per call.

### `get_account_balance`

Returns a single balance figure for a named account.

---

## Signal Source

`FinanceSignalSource` implements Ze's `SignalSource` protocol (Phase 60). It runs
inside the daily snapshot job after positions are refreshed.

| Signal | Trigger | Severity |
|--------|---------|----------|
| `finance.pnl_swing` | Total unrealised P&L changed by > 5% vs previous snapshot | `medium` |
| `finance.large_transaction` | Single transaction notional > `large_transaction_threshold` | `low` |

---

## Jobs

### `DailySnapshotJob`

Registered as a `ProactiveJob`. Runs on `finance.snapshot_schedule`.

1. For each configured `DataSource`, call `fetch_account()` and `fetch_positions()`.
2. Upsert into `finance_accounts` and `finance_positions`.
3. Fetch new transactions since the last known `settled_at` and append to
   `finance_transactions`.
4. Run `FinanceSignalSource` to emit any triggered signals.

---

## Data Domains (Phase 62 integration)

`FinancePlugin` implements `data_domains()` so the export / delete system covers
all finance tables. FK order: positions and transactions reference accounts, so
accounts are deleted last.

```python
def data_domains(self) -> list[DataDomain]:
    return [
        DataDomain(
            name="finance.transactions",
            export=lambda db: ...,  # SELECT * FROM finance_transactions
            delete=lambda db: ...,  # DELETE FROM finance_transactions
            delete_order=10,
            importer=lambda db, rows: ...,
        ),
        DataDomain(
            name="finance.positions",
            export=lambda db: ...,
            delete=lambda db: ...,
            delete_order=10,
            importer=lambda db, rows: ...,
        ),
        DataDomain(
            name="finance.csv_mappings",
            export=lambda db: ...,
            delete=lambda db: ...,
            delete_order=10,
            importer=lambda db, rows: ...,
        ),
        DataDomain(
            name="finance.accounts",
            export=lambda db: ...,
            delete=lambda db: ...,
            delete_order=20,  # deleted after child tables
            importer=lambda db, rows: ...,
        ),
    ]
```

Archive files produced: `finance.accounts.json`, `finance.positions.json`,
`finance.transactions.json`, `finance.csv_mappings.json`.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_sdk` | `BaseAgent`, `@agent`, `@tool`, `ProactiveJob`, `SignalSource`, `ZePlugin`, `DataDomain`, errors |
| `ze_trading212` | `Trading212Client` — wraps T212 REST API; declared via `integration_types()` |
| `asyncpg` | DB pool (injected via `DBPool` protocol) |

---

## Implementation Notes

- **Notional is the aggregation unit.** `Position.notional` must always be populated.
  Quantity and price vary across asset classes; notional is the only field the risk
  engine can meaningfully sum across equities, crypto, and cash.
- **Positions table is a snapshot, not a ledger.** Each sync overwrites positions
  for a given `(account_id, ticker)`. Use `finance_transactions` for history.
- **Transaction dedup key is `(account_id, external_id)`.** The CSV source generates
  `external_id` as a hash of (date, type, amount, description) when the source
  provides no stable ID.
- **`CategoryInferrer` runs keyword rules before any LLM call.** Only descriptions
  that fall through to "Other" are batched and sent to Anthropic. Amounts, dates, and
  account identifiers are never included. Categories are written to the DB at ingestion
  so `get_spending_summary` never triggers an LLM call at query time.
- **`CsvSchemaInferrer` sends header + samples only.** Real transaction amounts and
  descriptions never reach the LLM during schema inference. The cached `CsvMapping`
  is then applied entirely in Python.
- **`FactorTaxonomy` enum is the shared contract with `ze-risk`.** Future `ze-risk`
  imports this enum from `ze_finance.risk.types`. Finance owns the taxonomy.
- **`ze_trading212` is declared via `integration_types()`.** The Phase 63 integration
  framework wires `Trading212Client` into `FinancePlugin` at startup without any
  manual touch to `container.py`.
- **All LLM calls pin to `anthropic/claude-haiku-4-5-20251001`.** This includes the
  FinanceAgent and CsvSchemaInferrer. The global model config in `config.yaml` is
  intentionally ignored for this plugin.

---

## Open Questions

- [x] **Should `ze-risk` be a separate plugin or part of `ze-finance`?** — Separate
  plugin. Factor engine, signal ingestion (FRED, yfinance, GDELT), and drift detection
  are independently valuable. `ze-finance` owns the domain types and the DataSource
  contract; `ze-risk` imports from it.
- [x] **Notional currency.** — Store in position currency for now. Base-currency
  normalisation is deferred. The risk engine must handle multi-currency aggregation
  when it is introduced.
- [x] **Data protection / LLM provider.** — All LLM calls pinned to Anthropic (no
  training on API data). Data minimisation enforced at tool level: LLM sees aggregates,
  not raw rows.
- [x] **CSV column mapping.** — LLM-based schema inference on first import, cached to
  `finance_csv_mappings`. Only header + 5 sample rows sent to the model; no real data.
- [x] **Spending category inference.** — Two-tier `CategoryInferrer`: keyword rules
  run first (free, deterministic, no data exposure); transactions that remain "Other"
  are optionally forwarded to Anthropic haiku in batch when `finance.llm_categorization:
  true` is set. Only the description string is sent — no amounts, dates, or account
  identifiers. Category and source (`keyword` | `llm`) are stored at ingestion time in
  `finance_transactions.category` so no LLM call is made at query time.
- [x] **Large transaction threshold currency.** — The threshold is compared against the
  transaction's native currency value with no FX conversion. A config value of `500`
  means: flag any transaction ≥ 500 in whatever currency it was recorded in. Not
  currency-adjusted, but predictable and requires no FX data at signal-emission time.
  The signal payload includes the currency so the user sees "€620 at Booking.com" not
  "€620 (threshold: €500 equivalent)". Currency-normalised thresholds follow with
  multi-currency support.
