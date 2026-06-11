import json
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_personal.jobs.insights import InsightEngine
from ze_core.proactive.notifier import ProactiveNotifier


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_notifier():
    n = MagicMock(spec=ProactiveNotifier)
    n.push = AsyncMock()
    return n


def make_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=None)
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool, conn


def make_settings(extra_insights_mem: dict | None = None):
    s = MagicMock()
    s.memory_insights_config = {
        "lookback_days": 7,
        "min_evidence": 3,
        "max_per_run": 3,
        **(extra_insights_mem or {}),
    }
    s.proactive_config = {"insights": {"category_cooldown_days": 7}}
    s.config = {"models": {"insights": "anthropic/claude-haiku-4-5"}}
    return s


def make_engine(conn=None, notifier=None, client=None, settings=None):
    pool, c = make_pool(conn)
    return InsightEngine(
        notifier=notifier or make_notifier(),
        pool=pool,
        openrouter_client=client or AsyncMock(),
        settings=settings or make_settings(),
    ), c


def _fact_row(key="sleep", value="mentioned sleep problems"):
    return {"key": key, "value": value, "updated_at": None}


def _episode_row(summary="Had a long research session"):
    return {"summary": summary, "response": None, "created_at": None}


def _profile_row():
    return {
        "preferences": "prefers async communication",
        "habits": "reads in the morning",
        "topics": "distributed systems, sleep",
        "relationships": "",
        "goals": "learn Portuguese",
    }


def _insight_json(text="You've mentioned sleep four times.", category="pattern"):
    return json.dumps([{"text": text, "category": category}])


# ── Tests ──────────────────────────────────────────────────────────────────────

async def test_insights_generates_and_pushes():
    inserted_id = uuid4()
    conn = make_conn()
    # fetch call order: facts, episodes, recent_insights, pushed_categories
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],  # facts
        [_episode_row()],                          # episodes
        [],                                        # recent insights
        [],                                        # pushed categories
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _profile_row(),         # profile
        {"id": inserted_id},    # INSERT RETURNING id
    ])

    client = AsyncMock()
    client.complete = AsyncMock(return_value=_insight_json())
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_awaited_once()
    pushed_text = notifier.push.call_args[0][0]
    assert "sleep" in pushed_text.lower()
    # UPDATE should mark pushed
    conn.execute.assert_awaited_once()


async def test_insights_skips_sparse():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row()],  # facts — only 1
        [],             # episodes — 0
        [],             # recent insights
        [],             # pushed categories
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock()
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    client.complete.assert_not_awaited()
    notifier.push.assert_not_awaited()


async def test_insights_filters_category_cooldown():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [{"category": "pattern"}],  # "pattern" is on cooldown
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(return_value=_insight_json(category="pattern"))
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_not_awaited()


async def test_insights_caps_max_per_run():
    five_insights = json.dumps([
        {"text": f"Insight {i}", "category": "trend"} for i in range(5)
    ])
    inserted_id = uuid4()
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    conn.fetchrow = AsyncMock(side_effect=[
        _profile_row(),
        {"id": inserted_id},
        {"id": inserted_id},
        {"id": inserted_id},
    ])

    client = AsyncMock()
    client.complete = AsyncMock(return_value=five_insights)
    notifier = make_notifier()
    settings = make_settings({"max_per_run": 3})

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client, settings=settings)
    await engine.run()

    assert notifier.push.await_count == 3


async def test_insights_haiku_failure():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("API error"))
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_not_awaited()


async def test_insights_bad_json():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(return_value="not json at all")
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_not_awaited()


async def test_insights_empty_array():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(return_value="[]")
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_not_awaited()


async def test_insights_invalid_category_discarded():
    bad_item = json.dumps([{"text": "Something interesting.", "category": "other"}])
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(return_value=bad_item)
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    notifier.push.assert_not_awaited()


async def test_insights_passes_recent_to_llm():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [{"text": "You mentioned sleep a lot last week.", "category": "pattern"}],
        [],
    ])
    conn.fetchrow = AsyncMock(return_value=_profile_row())

    client = AsyncMock()
    client.complete = AsyncMock(return_value="[]")
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    call_kwargs = client.complete.call_args[1]
    user_prompt = call_kwargs.get("prompt", "")
    assert "You mentioned sleep a lot last week." in user_prompt


async def test_insights_no_profile_uses_placeholder():
    conn = make_conn()
    conn.fetch = AsyncMock(side_effect=[
        [_fact_row(), _fact_row(), _fact_row()],
        [_episode_row()],
        [],
        [],
    ])
    # profile row is None — all fields empty / missing
    conn.fetchrow = AsyncMock(return_value=None)

    client = AsyncMock()
    client.complete = AsyncMock(return_value="[]")
    notifier = make_notifier()

    engine, _ = make_engine(conn=conn, notifier=notifier, client=client)
    await engine.run()

    call_kwargs = client.complete.call_args[1]
    user_prompt = call_kwargs.get("prompt", "")
    assert "(no profile yet)" in user_prompt
