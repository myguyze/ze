import pathlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from ze.proactive.briefing import MorningBriefing
from ze.proactive.notifier import ProactiveNotifier
from ze.settings import Settings, get_settings


def make_settings():
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_notifier():
    n = MagicMock(spec=ProactiveNotifier)
    n.push = AsyncMock()
    return n


def make_conn(
    dedup_row=None,
    unreviewed=0,
    workflow_rows=None,
    failure_rows=None,
    stale_contact_rows=None,
):
    conn = AsyncMock()
    # fetchrow calls: dedup check, then unreviewed count
    conn.fetchrow = AsyncMock(
        side_effect=[
            dedup_row,
            {"n": unreviewed},
        ]
    )
    conn.fetch = AsyncMock(
        side_effect=[
            workflow_rows or [],
            failure_rows or [],
            stale_contact_rows or [],
        ]
    )
    conn.execute = AsyncMock()
    return conn


def make_pool(conn):
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_briefing(conn=None, notifier=None, settings=None):
    if conn is None:
        conn = make_conn()
    return MorningBriefing(
        notifier=notifier or make_notifier(),
        pool=make_pool(conn),
        settings=settings or make_settings(),
    ), conn


async def test_briefing_sends_stats():
    conn = make_conn(unreviewed=2, workflow_rows=[{"name": "daily_report"}])
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    notifier.push.assert_awaited_once()
    text = notifier.push.call_args[0][0]
    assert "Good morning" in text
    assert "Unreviewed facts: 2" in text
    assert "daily_report" in text


async def test_briefing_dedup_skips():
    conn = make_conn(dedup_row={"1": 1})  # push_log row found
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()
    notifier.push.assert_not_awaited()


async def test_briefing_includes_nudge_above_threshold():
    # Default threshold is 5; set 6 unreviewed
    conn = make_conn(unreviewed=6)
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "waiting for review" in text


async def test_briefing_no_nudge_below_threshold():
    conn = make_conn(unreviewed=2)
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "waiting for review" not in text


async def test_briefing_includes_failure_summary():
    failure = {"payload": "daily_report", "sent_at": datetime(2026, 5, 20, 2, 0, tzinfo=timezone.utc)}
    conn = make_conn(failure_rows=[failure])
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Recent failure" in text
    assert "daily_report" in text


async def test_briefing_writes_push_log():
    conn = make_conn()
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    conn.execute.assert_awaited_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO push_log" in sql
    assert "morning_brief" in sql


# ── follow-up nudges ──────────────────────────────────────────────────────────

async def test_briefing_includes_stale_contact_nudge():
    stale = [{"name": "João Silva", "days_ago": 14}]
    conn = make_conn(stale_contact_rows=stale)
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Follow-up nudges" in text
    assert "João Silva" in text
    assert "14 days ago" in text


async def test_briefing_no_nudge_when_no_stale_contacts():
    conn = make_conn(stale_contact_rows=[])
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Follow-up nudges" not in text


async def test_briefing_singular_day_in_nudge():
    stale = [{"name": "Ana Costa", "days_ago": 1}]
    conn = make_conn(stale_contact_rows=stale)
    notifier = make_notifier()
    b = MorningBriefing(notifier=notifier, pool=make_pool(conn), settings=make_settings())
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "1 day ago" in text
    assert "1 days ago" not in text
