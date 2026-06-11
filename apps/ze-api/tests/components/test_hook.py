from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ze_components.tools  # noqa: F401
from ze_api.hooks import ComponentCollectionHook
from ze_components import context as ctx
from ze_components.types import CardComponent
from ze_core.orchestration.hooks import LoopEndEvent, LoopStartEvent


def _make_ctx(session_id: str):
    c = MagicMock()
    c.session_id = session_id
    return c


def _make_loop_start(session_id: str) -> LoopStartEvent:
    return LoopStartEvent(agent_name="test", ctx=_make_ctx(session_id))


def _make_loop_end(session_id: str) -> LoopEndEvent:
    return LoopEndEvent(agent_name="test", ctx=_make_ctx(session_id), tool_calls=[], iterations_used=1)


async def test_on_loop_start_sets_fresh_context():
    hook = ComponentCollectionHook()
    event = _make_loop_start("s1")

    await hook.on_loop_start(event)
    ctx.append(CardComponent(body="test"))

    assert "s1" in hook._tokens


async def test_on_loop_end_drains_context_var():
    hook = ComponentCollectionHook()
    start = _make_loop_start("s1")
    end = _make_loop_end("s1")

    await hook.on_loop_start(start)
    ctx.append(CardComponent(body="hello"))
    await hook.on_loop_end(end)

    assert "s1" in hook._results
    assert hook._results["s1"][0]["body"] == "hello"


async def test_pop_components_returns_and_removes():
    hook = ComponentCollectionHook()
    start = _make_loop_start("s1")
    end = _make_loop_end("s1")

    await hook.on_loop_start(start)
    ctx.append(CardComponent(body="pop me"))
    await hook.on_loop_end(end)

    first = hook.pop_components("s1")
    second = hook.pop_components("s1")

    assert len(first) == 1
    assert second == []


async def test_concurrent_sessions_produce_independent_results():
    hook = ComponentCollectionHook()

    await hook.on_loop_start(_make_loop_start("session-a"))
    ctx.append(CardComponent(body="a"))
    await hook.on_loop_end(_make_loop_end("session-a"))

    await hook.on_loop_start(_make_loop_start("session-b"))
    ctx.append(CardComponent(body="b"))
    await hook.on_loop_end(_make_loop_end("session-b"))

    a = hook.pop_components("session-a")
    b = hook.pop_components("session-b")

    assert a[0]["body"] == "a"
    assert b[0]["body"] == "b"
