from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.telegram.commands import _fmt_tokens, _fmt_usd, costs_summary, memory_summary


# ── Formatting helpers ────────────────────────────────────────────────────────

def test_fmt_usd():
    assert _fmt_usd(0.0) == "$0.000"
    assert _fmt_usd(1.847) == "$1.847"
    assert _fmt_usd(0.012) == "$0.012"


def test_fmt_tokens_small():
    assert _fmt_tokens(999) == "999"


def test_fmt_tokens_thousands():
    assert _fmt_tokens(1_500) == "1.5K"


def test_fmt_tokens_millions():
    assert _fmt_tokens(1_200_000) == "1.2M"


# ── Pool helpers ──────────────────────────────────────────────────────────────

def _make_pool(month_rows, today_cost=None, facts=None, profile=None):
    """Build a mock asyncpg pool that returns preset query results."""
    conn = AsyncMock()

    # fetch() returns different values based on call order
    fetch_results = []
    if month_rows is not None:
        fetch_results.append(month_rows)
    if facts is not None:
        fetch_results.append(facts)

    fetch_call = 0

    async def _fetch(query, *args, **kwargs):
        nonlocal fetch_call
        result = fetch_results[fetch_call] if fetch_call < len(fetch_results) else []
        fetch_call += 1
        return result

    conn.fetch = _fetch

    fetchrow_results = []
    if today_cost is not None:
        fetchrow_results.append({"cost": today_cost})
    if profile is not None:
        fetchrow_results.append(profile)

    fetchrow_call = 0

    async def _fetchrow(query, *args, **kwargs):
        nonlocal fetchrow_call
        result = fetchrow_results[fetchrow_call] if fetchrow_call < len(fetchrow_results) else None
        fetchrow_call += 1
        return result

    conn.fetchrow = _fetchrow

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))
    return pool


# ── costs_summary ─────────────────────────────────────────────────────────────

async def test_costs_summary_no_rows():
    pool = _make_pool(month_rows=[], today_cost=Decimal("0"))
    result = await costs_summary(pool)
    assert result == "No costs recorded yet."


async def test_costs_summary_with_rows():
    rows = [
        {"agent": "research",  "cost": Decimal("0.389"), "calls": 50,  "tokens": 400_000},
        {"agent": "companion", "cost": Decimal("0.421"), "calls": 80,  "tokens": 500_000},
    ]
    pool = _make_pool(month_rows=rows, today_cost=Decimal("0.012"))
    result = await costs_summary(pool)

    assert "💰" in result
    assert "$0.012" in result           # today
    assert "$0.810" in result           # month total (0.389 + 0.421)
    assert "research" in result
    assert "companion" in result
    assert "Calls: 130" in result


async def test_costs_summary_unknown_agent_goes_to_other():
    rows = [
        {"agent": "memory_consolidator", "cost": Decimal("0.050"), "calls": 5, "tokens": 10_000},
    ]
    pool = _make_pool(month_rows=rows, today_cost=Decimal("0"))
    result = await costs_summary(pool)
    assert "other" in result
    assert "memory_consolidator" not in result


async def test_costs_summary_token_formatting():
    rows = [
        {"agent": "companion", "cost": Decimal("0.100"), "calls": 1, "tokens": 1_500_000},
    ]
    pool = _make_pool(month_rows=rows, today_cost=Decimal("0"))
    result = await costs_summary(pool)
    assert "1.5M" in result


# ── memory_summary ────────────────────────────────────────────────────────────

async def test_memory_summary_no_facts_no_profile():
    pool = _make_pool(month_rows=None, facts=[], profile=None)
    result = await memory_summary(pool)
    assert "No facts recorded yet." in result
    assert "Profile" not in result


async def test_memory_summary_with_facts():
    facts = [
        {"key": "name",     "value": "João"},
        {"key": "timezone", "value": "Europe/Lisbon"},
    ]
    pool = _make_pool(month_rows=None, facts=facts, profile=None)
    result = await memory_summary(pool)
    assert "(2)" in result
    assert "• name: João" in result
    assert "• timezone: Europe/Lisbon" in result


async def test_memory_summary_with_profile():
    facts = [{"key": "name", "value": "João"}]
    profile = {
        "preferences":   "concise replies",
        "habits":        "morning check-in",
        "topics":        "software engineering",
        "relationships": "",
        "goals":         "ship Ze",
    }
    pool = _make_pool(month_rows=None, facts=facts, profile=profile)
    result = await memory_summary(pool)
    assert "Profile" in result
    assert "Preferences" in result
    assert "concise replies" in result
    assert "Relationships" not in result   # empty field omitted


async def test_memory_summary_empty_profile_fields_omitted():
    facts = [{"key": "x", "value": "y"}]
    profile = {
        "preferences": "",
        "habits":      "",
        "topics":      "",
        "relationships": "",
        "goals":       "",
    }
    pool = _make_pool(month_rows=None, facts=facts, profile=profile)
    result = await memory_summary(pool)
    assert "Profile" not in result
