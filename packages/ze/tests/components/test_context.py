from __future__ import annotations

import asyncio
import dataclasses

import pytest

from ze_components import context as ctx
from ze_components.types import CardComponent, MetricComponent


def test_begin_and_collect_round_trip():
    token = ctx.begin_collection()
    ctx.append(MetricComponent(label="Cost", value="$5"))
    ctx.append(CardComponent(body="Info"))
    result = ctx.collect_and_reset(token)
    assert len(result) == 2
    assert result[0]["type"] == "metric"
    assert result[1]["type"] == "card"


def test_collect_resets_to_empty():
    token = ctx.begin_collection()
    ctx.append(CardComponent(body="x"))
    ctx.collect_and_reset(token)

    # After reset the var is at its prior state — begin again for a new collection
    token2 = ctx.begin_collection()
    result = ctx.collect_and_reset(token2)
    assert result == []


def test_append_outside_collection_noop():
    # Should not raise
    ctx.append(CardComponent(body="ignored"))


def test_collect_and_reset_with_no_appends():
    token = ctx.begin_collection()
    result = ctx.collect_and_reset(token)
    assert result == []


async def test_two_coroutines_collect_independently():
    """Each coroutine has its own ContextVar snapshot — no cross-contamination."""
    results: dict[str, list] = {}

    async def _task(name: str, component_body: str) -> None:
        token = ctx.begin_collection()
        await asyncio.sleep(0)  # yield to other coroutine
        ctx.append(CardComponent(body=component_body))
        results[name] = ctx.collect_and_reset(token)

    await asyncio.gather(
        _task("a", "from-a"),
        _task("b", "from-b"),
    )

    assert len(results["a"]) == 1
    assert results["a"][0]["body"] == "from-a"
    assert len(results["b"]) == 1
    assert results["b"][0]["body"] == "from-b"
