# Finance — Recurring Expense Detection — Spec

> **Package:** `ze-finance` (`plugins/ze-finance`)
> **Phase:** 70
> **Status:** Done

---

## Implementation Status

| Feature | Status |
|---------|--------|
| `RecurringExpense` type + `RecurringStatus` enum | ✅ Done |
| `RecurringStore` | ✅ Done |
| `RecurringDetector` | ✅ Done — generic gap analysis, snaps to natural intervals |
| `RecurringDetectionJob` | ✅ Done |
| Staleness check + CSV nudge | ✅ Done |
| `get_recurring_expenses` agent tool | ✅ Done |
| `confirm_recurring` / `dismiss_recurring` agent tools | ✅ Done |
| `render_confirm` review flow in FinanceAgent | ✅ Done — via tool list + instructions |
| Migration `zfin002` | ✅ Done |
| Opt-in config flag (`recurring_detection_enabled`) | ✅ Done — job only registers when `true`; `CapabilityGate` is not the right mechanism here (it controls agent execution modes, not job scheduling) |

---

## Purpose

Ze surfaces recurring charges automatically — subscriptions, rent, utility bills, food
delivery habits — so users can audit what they're paying every month without manually
reviewing their bank statements. This is an opt-in capability: Ze detects candidates
algorithmically from existing transaction history, asks the user to confirm or dismiss
them, and then maintains an up-to-date picture of fixed monthly commitments.

Detection is purely algorithmic (no LLM). The job also checks data freshness per
account, and when the data is stale, sends a conditional nudge asking the user to
upload a new CSV (for manual-import accounts) or logs an anomaly (for live-connected
accounts).

---

## Responsibilities

- Detect recurring expense candidates from transaction history using a grouping +
  frequency algorithm.
- Persist candidates in `finance_recurring` with a lifecycle status
  (`detected → confirmed | dismissed`).
- Run detection monthly via a proactive job.
- Before running detection, check data freshness per account:
  - **CSV-sourced accounts**: if newest transaction is older than `staleness_days`
    (default 35), skip detection for that account and send a push nudge asking the
    user to upload a fresh statement.
  - **Live-connected accounts** (Trading212, future open-banking): staleness here
    means the daily snapshot job failed; log an error, do not nudge the user.
- Expose recurring data via an agent tool so Ze can answer questions like "what
  subscriptions do I have?" and proactively comment on the monthly total.

---

## Out of Scope

- Cancellation flows (Ze cannot cancel subscriptions on the user's behalf).
- Annual or quarterly cadence detection (v1 targets monthly and weekly only).
- LLM-based detection — algorithmic grouping is sufficient and avoids data exposure.
- Any UI beyond push notifications and conversational responses.

---

## Module Location

```
plugins/ze-finance/
  ze_finance/
    recurring/
      __init__.py
      types.py       ← RecurringExpense, RecurringStatus, StalenessReport
      detector.py    ← RecurringDetector (pure, no I/O)
      store.py       ← RecurringStore (asyncpg)
    jobs/
      recurring.py   ← RecurringDetectionJob (@proactive_job)
    agents/
      finance/
        tools.py     ← add get_recurring_expenses
```

---

## Interface Contract

### `RecurringDetector`

```python
class RecurringDetector:
    def detect(self, transactions: list[Transaction]) -> list[RecurringExpense]:
        """
        Pure function — no I/O.
        Groups transactions by normalised merchant key, counts distinct months,
        returns candidates with ≥ MIN_OCCURRENCES hits and amount variance ≤ AMOUNT_TOLERANCE.
        """
```

Algorithm:
1. Filter to spending transactions only (`withdrawal`, `fee`; exclude `buy`/`sell`/`deposit`).
2. Normalise description: lowercase, strip numbers and punctuation, collapse whitespace.
3. Group by `(normalised_key, currency)`.
4. Per group: collect `(month, amount)` pairs across the lookback window (default 90 days).
5. If distinct months ≥ `MIN_OCCURRENCES` (default 2) and `std(amounts) / mean(amounts) ≤ AMOUNT_TOLERANCE` (default 0.10): emit a `RecurringExpense` candidate.
6. Set `cadence = "weekly"` if median inter-occurrence gap ≤ 10 days, else `"monthly"`.
7. `amount` = median of observed amounts (rounded to 2 dp).

### `RecurringStore`

```python
class RecurringStore:
    async def upsert_detected(self, candidates: list[RecurringExpense]) -> None:
        """Insert new candidates (status=detected). Skip if already confirmed/dismissed."""

    async def list(
        self,
        status: RecurringStatus | None = None,
    ) -> list[RecurringExpense]: ...

    async def confirm(self, key: str, account_id: str) -> None: ...
    async def dismiss(self, key: str, account_id: str) -> None: ...
    async def update_last_seen(self, key: str, account_id: str, seen_at: datetime) -> None: ...
```

`upsert_detected` semantics:
- If no row exists, insert with `status = detected`.
- If a row exists with `status = confirmed`: update `last_seen_at`, `amount`, and
  `occurrence_count` only — do not touch status.
- If a row exists with `status = dismissed`:
  - If `abs(new_amount - stored_amount) / stored_amount > price_change_threshold`:
    reset `status` to `detected`, update `amount` and `last_seen_at`, and return the
    row as a price-change candidate so the job can send a targeted push.
  - Otherwise: update `last_seen_at` only — keep dismissed.

### `RecurringDetectionJob`

```python
@proactive_job
class RecurringDetectionJob:
    job_id = "finance.recurring_detection"

    async def run(self) -> None:
        accounts = await self._portfolio_store.list_accounts()
        for account in accounts:
            report = await self._check_staleness(account)
            if report.is_stale:
                await self._handle_stale(account, report)
                continue
            await self._detect_and_surface(account)
```

Staleness threshold: `staleness_days` from config (default 35). This is intentionally
longer than a calendar month to allow for delayed uploads.

### Staleness handling

```python
async def _handle_stale(self, account: Account, report: StalenessReport) -> None:
    if _is_csv_source(account.source_id):
        # Send a nudge via ProactiveNotifier
        await self._notifier.send(
            title="Finance data needs updating",
            body=(
                f"I haven't seen new transactions for '{account.name}' in "
                f"{report.days_since_last} days. "
                "Upload a fresh bank statement so I can keep your recurring "
                "expense list up to date."
            ),
            tags=["finance", "action-needed"],
        )
    else:
        # Live source — daily snapshot should have caught this
        log.error(
            "finance_live_source_stale",
            account_id=account.id,
            source_id=account.source_id,
            days_since_last=report.days_since_last,
        )
```

`_is_csv_source(source_id)` returns `True` if `source_id.startswith("csv:")`.

The nudge is rate-limited: at most once per account per 14 days, tracked via a
`last_nudge_at` column on `finance_recurring_staleness` (see schema below).

### Surfacing new candidates

After detection, diff against what's already stored:

```python
async def _detect_and_surface(self, account: Account) -> None:
    transactions = await self._transaction_store.get(account_id=account.id, ...)
    candidates = self._detector.detect(transactions)
    upsert_result = await self._recurring_store.upsert_detected(candidates)

    if upsert_result.new_candidates:
        await self._notifier.send(
            title="New recurring charges spotted",
            body=_format_new_summary(upsert_result.new_candidates),
            tags=["finance"],
        )
    if upsert_result.price_changed:
        for item in upsert_result.price_changed:
            await self._notifier.send(
                title="Recurring charge changed",
                body=(
                    f"Your {item.merchant_display} charge changed from "
                    f"{item.currency} {item.previous_amount} to "
                    f"{item.currency} {item.amount} — still happy with it?"
                ),
                tags=["finance"],
            )
```

`_format_new_summary` produces a message like:

> I spotted 3 new recurring charges this month: Netflix €15.99, Bolt Food ~€24, and
> an unknown charge of €9.90. Want me to categorise these as subscriptions?

`upsert_detected` returns an `UpsertResult` dataclass:

```python
@dataclass
class UpsertResult:
    new_candidates: list[RecurringExpense]
    price_changed: list[RecurringExpense]  # includes previous_amount field
```

The agent (not the job) handles the conversational follow-up when the user responds.

---

## Data Structures

```python
# ze_finance/recurring/types.py

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class RecurringStatus(str, Enum):
    DETECTED   = "detected"    # found by algorithm, not yet reviewed
    CONFIRMED  = "confirmed"   # user said "yes, this is a subscription"
    DISMISSED  = "dismissed"   # user said "no, ignore this"


class Cadence(str, Enum):
    WEEKLY  = "weekly"
    MONTHLY = "monthly"


@dataclass
class RecurringExpense:
    normalised_key: str       # grouping key derived from description
    account_id: str
    merchant_display: str     # best human-readable label seen for this key
    amount: Decimal
    currency: str
    cadence: Cadence
    category: str             # inherited from categoriser, can be overridden
    status: RecurringStatus
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int


@dataclass
class StalenessReport:
    account_id: str
    is_stale: bool
    days_since_last: int      # 0 if no transactions at all (treat as stale)
    last_transaction_at: datetime | None
```

---

## Database Schema

Migration `zfin002_recurring`.

```sql
CREATE TABLE finance_recurring (
    normalised_key   TEXT        NOT NULL,
    account_id       TEXT        NOT NULL,
    merchant_display TEXT        NOT NULL,
    amount           NUMERIC     NOT NULL,
    currency         TEXT        NOT NULL,
    cadence          TEXT        NOT NULL,
    category         TEXT        NOT NULL DEFAULT 'Other',
    status           TEXT        NOT NULL DEFAULT 'detected',
    first_seen_at    TIMESTAMPTZ NOT NULL,
    last_seen_at     TIMESTAMPTZ NOT NULL,
    occurrence_count INTEGER     NOT NULL DEFAULT 1,
    PRIMARY KEY (normalised_key, account_id)
);

-- Rate-limits the CSV staleness nudge per account
CREATE TABLE finance_recurring_staleness (
    account_id    TEXT        PRIMARY KEY,
    last_nudge_at TIMESTAMPTZ NOT NULL
);
```

---

## Agent Tools

### `get_recurring_expenses`

```python
@tool(
    access=ToolAccess.READ,
    description=(
        "List recurring expenses and subscriptions Ze has detected. "
        "Returns confirmed and detected items. Use when the user asks about "
        "subscriptions, fixed costs, or recurring charges."
    ),
)
async def get_recurring_expenses(
    recurring_store: RecurringStore,
    status: str | None = None,   # "detected" | "confirmed" | "dismissed" | None (all)
) -> list[dict]:
    ...
```

Response shape per item:

```json
{
  "merchant": "Netflix",
  "amount": "15.99",
  "currency": "EUR",
  "cadence": "monthly",
  "category": "Entertainment",
  "status": "confirmed",
  "last_seen": "2026-06-01"
}
```

### `confirm_recurring` / `dismiss_recurring`

```python
@tool(access=ToolAccess.WRITE, description="Mark a detected recurring charge as confirmed by the user.")
async def confirm_recurring(
    recurring_store: RecurringStore,
    normalised_key: str,
    account_id: str,
) -> str: ...

@tool(access=ToolAccess.WRITE, description="Dismiss a detected recurring charge — Ze will not surface it again.")
async def dismiss_recurring(
    recurring_store: RecurringStore,
    normalised_key: str,
    account_id: str,
) -> str: ...
```

### Review flow

When the proactive job surfaces new candidates, the agent uses `render_confirm` from
`ze_components.tools` to render a button card per candidate (or a grouped batch card):

```
"Is this a subscription you want to track?"
  Netflix — €15.99/month  [Yes, track it]  [Ignore]
```

The button tap returns as a plain text message ("Yes, track it" / "Ignore").
The agent receives that message, matches it back to the pending candidate, and calls
`confirm_recurring` or `dismiss_recurring` accordingly.

For a batch of candidates (≥2), the agent renders a `render_list` of all candidates
followed by a `render_confirm` with "Review all" / "Dismiss all" actions, then steps
through them one at a time in conversation.

---

## Configuration

```yaml
# config/config.yaml
finance:
  recurring_detection_schedule: "0 9 1 * *"   # 1st of each month, 09:00
  recurring_staleness_days: 35                 # accounts older than this get a nudge
  recurring_nudge_cooldown_days: 14            # minimum days between nudges per account
  recurring_price_change_threshold: 0.10      # resurface dismissed items if amount changes by >10%
```

Opt-in capability key: `finance.recurring_detection`.
When the capability is disabled (default), `RecurringDetectionJob` exits immediately
at the top of `run()`. The user enables it by saying something like "track my recurring
expenses" — the `FinanceAgent` enables the capability via `CapabilityGate` and
triggers a one-shot detection run.

---

## Dependencies

| Dependency | Purpose |
|------------|---------|
| `ze_finance.store.TransactionStore` | Fetch transactions for lookback window |
| `ze_finance.store.PortfolioStore` | List accounts + check source_id |
| `ze_proactive.notifier.ProactiveNotifier` | Send push nudges |
| `ze_sdk.capability.CapabilityGate` | Opt-in gate |

---

## Implementation Notes

- `_is_csv_source` checks `source_id.startswith("csv:")`. The convention is set by
  `CsvDataSource` in `sources/csv.py`; do not change the prefix without updating this check.
- The detector is pure (no I/O) so it can be unit-tested without a DB or network.
- `upsert_detected` must never overwrite `confirmed` or `dismissed` status — user
  decisions are sticky. Only `last_seen_at`, `amount`, and `occurrence_count` update.
- The nudge message must not include the account balance or any amount totals — only
  the fact that data is stale. This keeps the push notification safe to display on a
  lock screen.
- The candidate summary notification may include amounts and merchant names — these
  are less sensitive than balances and are the point of the feature.

---

## Open Questions

- [x] Dismissed candidates resurface when the amount changes by more than
  `recurring_price_change_threshold` (default 10%). Ze resets the status to `detected`
  and sends a push: *"Your Netflix charge changed from €15.99 to €17.99 — still happy
  with it?"* Below the threshold, dismissed stays dismissed.
- [x] confirm/dismiss uses `render_confirm` component buttons. The tap value is
  returned as a plain message; the agent then calls `confirm_recurring` /
  `dismiss_recurring` to persist the decision. No separate confirmation framework.
- [ ] cadence detection for annual plans: deferred to a future phase. Annual charges
  appear only once in a 90-day window and will not be detected by v1.
- [ ] semantic merchant merging: Phase 81 adds NLI-backed alias merging before
  `_normalise(tx.notes)` grouping (`NETFLIX.COM` / `Netflix` / `NETFLIX SUBSCRIPTION`).
