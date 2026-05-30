import pathlib
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from ze_core.contacts.types import StaleFollowUpNudge
from ze.jobs.briefing import MorningBriefing
from ze_core.proactive.push_log_store import PushLogEntry
from ze.settings import Settings, get_settings
from ze_core.proactive.notifier import ProactiveNotifier


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


def make_briefing(
    *,
    dedup=False,
    unreviewed=0,
    workflows=None,
    failures=None,
    stale_contacts=None,
    notifier=None,
    settings=None,
):
    push_log = MagicMock()
    push_log.was_sent_within_hours = AsyncMock(return_value=dedup)
    push_log.list_workflow_failures_within_hours = AsyncMock(return_value=failures or [])
    push_log.log = AsyncMock()

    memory = MagicMock()
    memory.count_unreviewed_facts = AsyncMock(return_value=unreviewed)

    workflow_store = MagicMock()
    workflow_store.list_enabled_scheduled = AsyncMock(return_value=workflows or [])

    person_store = MagicMock()
    person_store.list_stale_for_follow_up = AsyncMock(return_value=stale_contacts or [])

    b = MorningBriefing(
        notifier=notifier or make_notifier(),
        push_log_store=push_log,
        memory_store=memory,
        workflow_store=workflow_store,
        person_store=person_store,
        settings=settings or make_settings(),
    )
    return b, push_log


async def test_briefing_sends_stats():
    notifier = make_notifier()
    w = MagicMock()
    w.name = "daily_report"
    workflows = [w]
    b, _ = make_briefing(unreviewed=2, workflows=workflows, notifier=notifier)
    await b.run()

    notifier.push.assert_awaited_once()
    text = notifier.push.call_args[0][0]
    assert "Good morning" in text
    assert "Unreviewed facts: 2" in text
    assert "daily_report" in text


async def test_briefing_dedup_skips():
    notifier = make_notifier()
    b, push_log = make_briefing(dedup=True, notifier=notifier)
    await b.run()
    notifier.push.assert_not_awaited()
    push_log.log.assert_not_awaited()


async def test_briefing_includes_nudge_above_threshold():
    notifier = make_notifier()
    b, _ = make_briefing(unreviewed=6, notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "waiting for review" in text


async def test_briefing_no_nudge_below_threshold():
    notifier = make_notifier()
    b, _ = make_briefing(unreviewed=2, notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "waiting for review" not in text


async def test_briefing_includes_failure_summary():
    notifier = make_notifier()
    failures = [
        PushLogEntry(
            event_type="workflow_failure:abc",
            payload="daily_report",
            sent_at=datetime(2026, 5, 20, 2, 0, tzinfo=timezone.utc),
        )
    ]
    b, _ = make_briefing(failures=failures, notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Recent failure" in text
    assert "daily_report" in text


async def test_briefing_writes_push_log():
    notifier = make_notifier()
    b, push_log = make_briefing(notifier=notifier)
    await b.run()

    push_log.log.assert_awaited_once_with("morning_brief")


async def test_briefing_includes_stale_contact_nudge():
    notifier = make_notifier()
    stale = [StaleFollowUpNudge(name="João Silva", days_ago=14)]
    b, _ = make_briefing(stale_contacts=stale, notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Follow-up nudges" in text
    assert "João Silva" in text
    assert "14 days ago" in text


async def test_briefing_no_nudge_when_no_stale_contacts():
    notifier = make_notifier()
    b, _ = make_briefing(stale_contacts=[], notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Follow-up nudges" not in text


async def test_briefing_singular_day_in_nudge():
    notifier = make_notifier()
    stale = [StaleFollowUpNudge(name="Ana Costa", days_ago=1)]
    b, _ = make_briefing(stale_contacts=stale, notifier=notifier)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "1 day ago" in text
    assert "1 days ago" not in text
