from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from ze_personal.contacts.types import StaleFollowUpNudge
from ze_personal.jobs.briefing import MorningBriefing
from ze_core.proactive.push_log_store import PushLogEntry
from ze_core.settings import Settings
from ze_core.proactive.notifier import ProactiveNotifier
from ze_news.types import Article


def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
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
    news_store=None,
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
        news_store=news_store,
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


async def test_briefing_includes_headlines_when_news_store_present():
    notifier = make_notifier()
    articles = [
        Article(
            url="https://bbc.com/1",
            source_key="bbc_world",
            title="Global Summit Concludes",
            summary="Leaders reached an agreement.",
            published_at=datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc),
            tags=["global"],
        ),
        Article(
            url="https://bbc.com/2",
            source_key="bbc_tech",
            title="AI Chip Breakthrough",
            summary="New chip doubles performance.",
            published_at=datetime(2026, 6, 7, 7, 0, tzinfo=timezone.utc),
            tags=["global", "tech"],
        ),
    ]
    news_store = MagicMock()
    news_store.get_recent = AsyncMock(return_value=articles)

    b, _ = make_briefing(notifier=notifier, news_store=news_store)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Headlines" in text
    assert "Global Summit Concludes" in text
    assert "AI Chip Breakthrough" in text
    assert "bbc_world" in text
    news_store.get_recent.assert_awaited_once()


async def test_briefing_omits_headlines_when_news_store_absent():
    notifier = make_notifier()
    b, _ = make_briefing(notifier=notifier, news_store=None)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Headlines" not in text


async def test_briefing_omits_headlines_when_store_returns_empty():
    notifier = make_notifier()
    news_store = MagicMock()
    news_store.get_recent = AsyncMock(return_value=[])

    b, _ = make_briefing(notifier=notifier, news_store=news_store)
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Headlines" not in text


def make_briefing_with_personalization(
    *,
    notifier=None,
    news_store=None,
    memory_store=None,
    goal_store=None,
    dedup=False,
):
    push_log = MagicMock()
    push_log.was_sent_within_hours = AsyncMock(return_value=dedup)
    push_log.list_workflow_failures_within_hours = AsyncMock(return_value=[])
    push_log.log = AsyncMock()

    memory = memory_store or MagicMock()
    if not isinstance(memory, MagicMock) or not hasattr(memory.count_unreviewed_facts, "_mock_name"):
        memory = MagicMock()
    memory.count_unreviewed_facts = AsyncMock(return_value=0)

    workflow_store = MagicMock()
    workflow_store.list_enabled_scheduled = AsyncMock(return_value=[])

    person_store = MagicMock()
    person_store.list_stale_for_follow_up = AsyncMock(return_value=[])

    b = MorningBriefing(
        notifier=notifier or make_notifier(),
        push_log_store=push_log,
        memory_store=memory_store or memory,
        workflow_store=workflow_store,
        person_store=person_store,
        settings=make_settings(),
        news_store=news_store,
        goal_store=goal_store,
    )
    return b


async def test_briefing_personalized_shows_relevant_and_discovery():
    notifier = make_notifier()

    relevant_articles = [
        Article(
            url="https://bbc.com/1",
            source_key="bbc_tech",
            title="AI Chip Breakthrough",
            summary="New chip doubles performance.",
            published_at=datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc),
            tags=["global", "tech"],
        )
    ]
    discovery_articles = [
        Article(
            url="https://bbc.com/2",
            source_key="bbc_world",
            title="Global Summit Concludes",
            summary="Leaders reached an agreement.",
            published_at=datetime(2026, 6, 7, 7, 0, tzinfo=timezone.utc),
            tags=["global"],
        )
    ]

    news_store = MagicMock()
    news_store.get_personalized = AsyncMock(return_value=(relevant_articles, discovery_articles))

    memory_store = MagicMock()
    memory_store.count_unreviewed_facts = AsyncMock(return_value=0)
    # No facts → fact_count=0 → header says "Headlines:" (not "For you:")
    memory_store.list_recent_facts = AsyncMock(return_value=[])

    b = make_briefing_with_personalization(
        notifier=notifier,
        news_store=news_store,
        memory_store=memory_store,
    )
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "AI Chip Breakthrough" in text
    assert "Outside your usual" in text
    assert "Global Summit Concludes" in text


async def test_briefing_personalized_shows_only_relevant_when_no_discovery():
    notifier = make_notifier()

    relevant_articles = [
        Article(
            url="https://bbc.com/1",
            source_key="bbc_tech",
            title="AI Chip Breakthrough",
            summary="New chip doubles performance.",
            published_at=datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc),
            tags=["global", "tech"],
        )
    ]

    news_store = MagicMock()
    news_store.get_personalized = AsyncMock(return_value=(relevant_articles, []))

    memory_store = MagicMock()
    memory_store.count_unreviewed_facts = AsyncMock(return_value=0)
    memory_store.list_recent_facts = AsyncMock(return_value=[])

    b = make_briefing_with_personalization(
        notifier=notifier,
        news_store=news_store,
        memory_store=memory_store,
    )
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "AI Chip Breakthrough" in text
    assert "Outside your usual" not in text


async def test_briefing_personalized_header_when_sufficient_facts():
    from ze_memory.types import Fact

    notifier = make_notifier()
    relevant_articles = [
        Article(
            url="https://bbc.com/1",
            source_key="bbc_tech",
            title="AI News",
            summary="AI advances.",
            published_at=datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc),
            tags=["global"],
        )
    ]
    news_store = MagicMock()
    news_store.get_personalized = AsyncMock(return_value=(relevant_articles, []))

    facts = [
        Fact(predicate=f"interest_{i}", value=f"topic_{i}")
        for i in range(6)
    ]
    memory_store = MagicMock()
    memory_store.count_unreviewed_facts = AsyncMock(return_value=0)
    memory_store.list_recent_facts = AsyncMock(return_value=facts)

    b = make_briefing_with_personalization(
        notifier=notifier,
        news_store=news_store,
        memory_store=memory_store,
    )
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "For you (based on your interests)" in text


async def test_briefing_personalized_fallback_on_get_personalized_error():
    notifier = make_notifier()
    articles = [
        Article(
            url="https://bbc.com/1",
            source_key="bbc_world",
            title="Fallback Headline",
            summary="Fallback.",
            published_at=datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc),
            tags=["global"],
        )
    ]
    news_store = MagicMock()
    news_store.get_personalized = AsyncMock(side_effect=Exception("db error"))
    news_store.get_recent = AsyncMock(return_value=articles)

    memory_store = MagicMock()
    memory_store.count_unreviewed_facts = AsyncMock(return_value=0)
    memory_store.list_recent_facts = AsyncMock(return_value=[])

    b = make_briefing_with_personalization(
        notifier=notifier,
        news_store=news_store,
        memory_store=memory_store,
    )
    await b.run()

    text = notifier.push.call_args[0][0]
    assert "Fallback Headline" in text
    news_store.get_recent.assert_awaited_once()
