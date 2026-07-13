from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from ze_seed.context import SeedContext
from ze_seed.domain import SeedDomain
from ze_seed.service import DevDataSeeder


@pytest.mark.asyncio
async def test_apply_runs_domains_in_descending_seed_order():
    order: list[str] = []

    async def clear_a(_ctx: SeedContext) -> None:
        order.append("clear-a")

    async def apply_a(_ctx: SeedContext) -> int:
        order.append("apply-a")
        return 1

    async def clear_b(_ctx: SeedContext) -> None:
        order.append("clear-b")

    async def apply_b(_ctx: SeedContext) -> int:
        order.append("apply-b")
        return 2

    domains = [
        SeedDomain("a", seed_order=10, clear=clear_a, apply=apply_a),
        SeedDomain("b", seed_order=20, clear=clear_b, apply=apply_b),
    ]
    seeder = DevDataSeeder(domains)
    ctx = SeedContext(
        pool=AsyncMock(),
        memory_store=AsyncMock(),
        embedder=AsyncMock(),
        goal_store=None,
        message_store=AsyncMock(),
        session_store=AsyncMock(),
    )

    results = await seeder.apply(ctx, force=True)

    assert order == ["clear-a", "clear-b", "apply-b", "apply-a"]
    assert results == {"a": 1, "b": 2}


@pytest.mark.asyncio
async def test_apply_skips_clear_when_force_false():
    cleared = False

    async def clear(_ctx: SeedContext) -> None:
        nonlocal cleared
        cleared = True

    async def apply(_ctx: SeedContext) -> int:
        return 3

    seeder = DevDataSeeder(
        [
            SeedDomain("only", seed_order=10, clear=clear, apply=apply),
        ]
    )
    ctx = SeedContext(
        pool=AsyncMock(),
        memory_store=AsyncMock(),
        embedder=AsyncMock(),
        goal_store=None,
        message_store=AsyncMock(),
        session_store=AsyncMock(),
    )

    await seeder.apply(ctx, force=False)

    assert cleared is False
