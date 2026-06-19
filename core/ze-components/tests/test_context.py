from __future__ import annotations

import asyncio

from ze_components import context as ctx
from ze_components.atoms import text
from ze_components.molecules import col


def test_begin_and_collect_round_trip():
    token = ctx.begin_collection()
    ctx.append(col([text("metric")]))
    ctx.append(text("info"))
    result = ctx.collect_and_reset(token)
    assert len(result) == 2
    assert result[0]["type"] == "col"
    assert result[1]["type"] == "text"


def test_collect_resets_to_empty():
    token = ctx.begin_collection()
    ctx.append(text("x"))
    ctx.collect_and_reset(token)

    token2 = ctx.begin_collection()
    result = ctx.collect_and_reset(token2)
    assert result == []


def test_append_outside_collection_noop():
    ctx.append(text("ignored"))


def test_collect_and_reset_with_no_appends():
    token = ctx.begin_collection()
    result = ctx.collect_and_reset(token)
    assert result == []


async def test_two_coroutines_collect_independently():
    """Each coroutine has its own ContextVar snapshot — no cross-contamination."""
    results: dict[str, list] = {}

    async def _task(name: str, content: str) -> None:
        token = ctx.begin_collection()
        await asyncio.sleep(0)
        ctx.append(text(content))
        results[name] = ctx.collect_and_reset(token)

    await asyncio.gather(
        _task("a", "from-a"),
        _task("b", "from-b"),
    )

    assert len(results["a"]) == 1
    assert results["a"][0]["content"] == "from-a"
    assert len(results["b"]) == 1
    assert results["b"][0]["content"] == "from-b"
