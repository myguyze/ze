from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from ze_agents.tool import ToolAccess, tool
from ze_finance.store import PortfolioStore, TransactionStore

_MAX_TRANSACTIONS = 50


@tool(
    access=ToolAccess.READ,
    description=(
        "Get portfolio summary: total notional, total unrealised P&L, and per-account breakdown. "
        "Set include_positions=True to include individual ticker-level positions."
    ),
)
async def get_portfolio_summary(
    portfolio_store: PortfolioStore,
    include_positions: bool = False,
) -> dict:
    accounts = await portfolio_store.list_accounts()
    all_positions = await portfolio_store.get_positions()

    total_notional = Decimal("0")
    total_pnl = Decimal("0")
    account_map: dict[str, dict] = {}

    for account in accounts:
        account_map[account.id] = {
            "name": account.name,
            "notional": Decimal("0"),
            "unrealised_pnl": Decimal("0"),
            "position_count": 0,
            "updated_at": account.updated_at.isoformat() if account.updated_at else None,
        }

    for pos in all_positions:
        total_notional += pos.notional
        total_pnl += pos.unrealised_pnl
        if pos.account_id in account_map:
            account_map[pos.account_id]["notional"] += pos.notional
            account_map[pos.account_id]["unrealised_pnl"] += pos.unrealised_pnl
            account_map[pos.account_id]["position_count"] += 1

    total_pnl_pct = (
        (total_pnl / total_notional * 100).quantize(Decimal("0.01"))
        if total_notional > 0
        else Decimal("0")
    )

    result: dict[str, Any] = {
        "total_notional": str(total_notional.quantize(Decimal("0.01"))),
        "total_unrealised_pnl": str(total_pnl.quantize(Decimal("0.01"))),
        "total_unrealised_pnl_pct": str(total_pnl_pct),
        "accounts": [
            {
                "name": v["name"],
                "notional": str(v["notional"].quantize(Decimal("0.01"))),
                "unrealised_pnl": str(v["unrealised_pnl"].quantize(Decimal("0.01"))),
                "position_count": v["position_count"],
                "updated_at": v["updated_at"],
            }
            for v in account_map.values()
        ],
    }

    if include_positions:
        result["positions"] = [
            {
                "ticker": p.asset.ticker,
                "name": p.asset.name,
                "asset_class": p.asset.asset_class.value,
                "quantity": str(p.quantity),
                "notional": str(p.notional.quantize(Decimal("0.01"))),
                "unrealised_pnl": f"{'+' if p.unrealised_pnl >= 0 else ''}{p.unrealised_pnl.quantize(Decimal('0.01'))}",
                "unrealised_pnl_pct": _pnl_pct(p.unrealised_pnl, p.notional - p.unrealised_pnl),
            }
            for p in all_positions
        ]

    return result


@tool(
    access=ToolAccess.READ,
    description="Get individual positions for an account. Use when the user asks about specific holdings.",
)
async def get_positions(
    portfolio_store: PortfolioStore,
    account_id: str | None = None,
) -> list[dict]:
    positions = await portfolio_store.get_positions(account_id=account_id)
    return [
        {
            "ticker": p.asset.ticker,
            "name": p.asset.name,
            "asset_class": p.asset.asset_class.value,
            "quantity": str(p.quantity),
            "notional": str(p.notional.quantize(Decimal("0.01"))),
            "unrealised_pnl": f"{'+' if p.unrealised_pnl >= 0 else ''}{p.unrealised_pnl.quantize(Decimal('0.01'))}",
            "unrealised_pnl_pct": _pnl_pct(p.unrealised_pnl, p.notional - p.unrealised_pnl),
        }
        for p in positions
    ]


@tool(
    access=ToolAccess.READ,
    description=(
        "Aggregate bank transactions into spending categories for a period. "
        "Default: current calendar month. Use for spending questions."
    ),
)
async def get_spending_summary(
    transaction_store: TransactionStore,
    account_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    since_dt = _parse_or_default(since, now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    until_dt = _parse_or_default(until, now)

    summaries = await transaction_store.spending_by_category(
        since=since_dt, until=until_dt, account_id=account_id
    )
    total = sum(s.total for s in summaries)
    currency = summaries[0].currency if summaries else "EUR"

    return {
        "period": f"{since_dt.date()} to {until_dt.date()}",
        "total_spent": str(total.quantize(Decimal("0.01"))),
        "currency": currency,
        "categories": [
            {
                "category": s.category,
                "total": str(s.total.quantize(Decimal("0.01"))),
                "count": s.transaction_count,
            }
            for s in summaries
        ],
    }


@tool(
    access=ToolAccess.READ,
    description=(
        "Get individual transactions. Use only when the user asks for specific transaction details. "
        "Capped at 50 rows."
    ),
)
async def get_transactions(
    transaction_store: TransactionStore,
    account_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 20,
) -> list[dict]:
    since_dt = _parse_or_default(since, None)
    until_dt = _parse_or_default(until, None)
    effective_limit = min(limit, _MAX_TRANSACTIONS)

    transactions = await transaction_store.get(
        account_id=account_id,
        since=since_dt,
        until=until_dt,
        limit=effective_limit,
    )
    return [
        {
            "id": tx.id,
            "type": tx.transaction_type.value,
            "amount": str((tx.quantity * tx.price).quantize(Decimal("0.01"))),
            "currency": tx.currency,
            "settled_at": tx.settled_at.isoformat(),
            "description": tx.notes,
            "ticker": tx.asset.ticker if tx.asset else None,
        }
        for tx in transactions
    ]


@tool(
    access=ToolAccess.READ,
    description="Get the current cash balance for a named account.",
)
async def get_account_balance(
    portfolio_store: PortfolioStore,
    account_id: str,
) -> dict:
    account = await portfolio_store.get_account(account_id)
    if account is None:
        return {"error": f"Account '{account_id}' not found."}
    return {
        "account": account.name,
        "balance": str(account.balance.quantize(Decimal("0.01"))),
        "currency": account.currency,
        "updated_at": account.updated_at.isoformat(),
    }


def _pnl_pct(pnl: Decimal, cost_basis: Decimal) -> str:
    if cost_basis == 0:
        return "0.0"
    pct = (pnl / cost_basis * 100).quantize(Decimal("0.1"))
    return f"{'+' if pct >= 0 else ''}{pct}"


def _parse_or_default(value: str | None, default: datetime | None) -> datetime | None:
    if value is None:
        return default
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return default
