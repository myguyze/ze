import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_core.proactive.notifier import ProactiveNotifier
from ze_calendar.reminders.calendar import (
    CalendarReminderService,
    _human_offset,
    _parse_interval,
)
from ze_calendar.reminders.calendar_store import CalendarReminderStore
from ze_api.settings import Settings, get_settings
from ze_personal.workflow.scheduler import WorkflowScheduler
from ze_personal.workflow.types import Workflow
from ze_core.proactive.push_log_store import PushLogStore


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def make_workflow_scheduler():
    sched = MagicMock(spec=WorkflowScheduler)
    sched.schedule_at = MagicMock()
    sched.remove_job_if_exists = MagicMock()
    return sched


def make_reminder_service(conn=None, notifier=None, client=None, settings=None):
    pool, c = make_pool(conn)
    store = MagicMock(spec=CalendarReminderStore)
    store.list_for_event = AsyncMock(return_value=[])
    store.list_unsent = AsyncMock(return_value=[])
    store.create = AsyncMock(return_value=uuid4())
    store.mark_sent = AsyncMock(return_value=None)
    store.delete_unsent_for_event = AsyncMock(return_value=[])
    push_log = MagicMock(spec=PushLogStore)
    push_log.log = AsyncMock()
    return CalendarReminderService(
        notifier=notifier or make_notifier(),
        store=store,
        push_log_store=push_log,
        openrouter_client=client or AsyncMock(),
        scheduler=make_workflow_scheduler(),
        settings=settings or make_settings(),
    ), c


def _future(minutes=60) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def _make_event(event_id=None, title="Meeting", start_offset_hours=2, updated_offset_hours=-1):
    start = datetime.now(timezone.utc) + timedelta(hours=start_offset_hours)
    updated = datetime.now(timezone.utc) + timedelta(hours=updated_offset_hours)
    return {
        "id": event_id or "evt_001",
        "summary": title,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(hours=1)).isoformat()},
        "updated": updated.isoformat(),
    }


# ── _parse_interval ───────────────────────────────────────────────────────────

def test_parse_interval_hours():
    td = _parse_interval("2 hours")
    assert td == timedelta(hours=2)


def test_parse_interval_minutes():
    td = _parse_interval("30 minutes")
    assert td == timedelta(minutes=30)


def test_parse_interval_days():
    td = _parse_interval("3 days")
    assert td == timedelta(days=3)


def test_parse_interval_weeks():
    td = _parse_interval("1 week")
    assert td == timedelta(weeks=1)


def test_parse_interval_singular():
    assert _parse_interval("1 hour") == timedelta(hours=1)
    assert _parse_interval("1 day") == timedelta(days=1)


def test_parse_interval_rejects_too_short():
    assert _parse_interval("1 minute") is None   # < 5 min minimum


def test_parse_interval_rejects_too_long():
    assert _parse_interval("15 days") is None


def test_parse_interval_rejects_invalid():
    assert _parse_interval("soon") is None
    assert _parse_interval("") is None


# ── _human_offset ─────────────────────────────────────────────────────────────

def test_human_offset_minutes():
    assert _human_offset(timedelta(minutes=30)) == "30 minutes"


def test_human_offset_hours():
    assert _human_offset(timedelta(hours=2)) == "2 hours"


def test_human_offset_days():
    assert _human_offset(timedelta(days=3)) == "3 days"


def test_human_offset_weeks():
    assert _human_offset(timedelta(weeks=2)) == "2 weeks"


# ── _assess_intervals ─────────────────────────────────────────────────────────

async def test_assess_intervals_parses_json():
    client = AsyncMock()
    client.complete = AsyncMock(return_value='{"intervals": ["2 hours", "30 minutes"]}')
    svc, _ = make_reminder_service(client=client)

    now = datetime.now(timezone.utc)
    event = _make_event(start_offset_hours=5)
    start_time = now + timedelta(hours=5)
    result = await svc._assess_intervals(event, start_time, now)

    assert len(result) == 2
    offsets = [td for td, _ in result]
    assert timedelta(hours=2) in offsets
    assert timedelta(minutes=30) in offsets


async def test_assess_intervals_fallback_on_haiku_error():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("API error"))
    svc, _ = make_reminder_service(client=client)

    now = datetime.now(timezone.utc)
    event = _make_event(start_offset_hours=5)
    start_time = now + timedelta(hours=5)
    result = await svc._assess_intervals(event, start_time, now)

    # Falls back to ["1 hour"]
    assert len(result) == 1
    assert result[0][0] == timedelta(hours=1)


async def test_assess_intervals_discards_past():
    client = AsyncMock()
    # Event starts in 30 minutes; "1 hour" interval → fire_at = -30 min (past)
    client.complete = AsyncMock(return_value='{"intervals": ["1 hour"]}')
    svc, _ = make_reminder_service(client=client)

    now = datetime.now(timezone.utc)
    start_time = now + timedelta(minutes=30)
    event = _make_event(start_offset_hours=0.5)
    result = await svc._assess_intervals(event, start_time, now)

    assert result == []


# ── sync ──────────────────────────────────────────────────────────────────────

async def test_sync_skips_when_no_credentials():
    svc, conn = make_reminder_service()
    await svc.sync(credentials=None)
    conn.fetch.assert_not_awaited()
    conn.fetchrow.assert_not_awaited()


async def test_sync_schedules_new_event():
    reminder_id = uuid4()
    store = MagicMock(spec=CalendarReminderStore)
    store.list_for_event = AsyncMock(return_value=[])
    store.create = AsyncMock(return_value=reminder_id)

    client = AsyncMock()
    client.complete = AsyncMock(return_value='{"intervals": ["1 hour"]}')
    notifier = make_notifier()
    sched = make_workflow_scheduler()

    fake_creds = MagicMock()
    service_mock = MagicMock()
    fake_creds.calendar = MagicMock(return_value=service_mock)
    event = _make_event(start_offset_hours=5)
    service_mock.events.return_value.list.return_value.execute.return_value = {"items": [event]}

    svc = CalendarReminderService(
        notifier=notifier,
        store=store,
        push_log_store=MagicMock(spec=PushLogStore),
        openrouter_client=client,
        scheduler=sched,
        settings=make_settings(),
    )
    await svc.sync(fake_creds)

    sched.schedule_at.assert_called_once()
    notifier.push.assert_awaited_once()
    assert "Reminders set" in notifier.push.call_args[0][0]


async def test_sync_skips_known_event():
    from ze_calendar.reminders.calendar_store import CalendarReminder
    assessed_at = datetime.now(timezone.utc)
    existing = CalendarReminder(
        id=uuid4(), event_id="evt_001", event_title="Meeting",
        fire_at=_future(), label="label", sent=False,
        assessed_at=assessed_at + timedelta(hours=1),  # assessed AFTER event update
    )
    store = MagicMock(spec=CalendarReminderStore)
    store.list_for_event = AsyncMock(return_value=[existing])

    client = AsyncMock()
    notifier = make_notifier()

    fake_creds = MagicMock()
    service_mock = MagicMock()
    fake_creds.calendar = MagicMock(return_value=service_mock)
    event = _make_event(start_offset_hours=5, updated_offset_hours=-2)
    service_mock.events.return_value.list.return_value.execute.return_value = {"items": [event]}

    svc = CalendarReminderService(
        notifier=notifier,
        store=store,
        push_log_store=MagicMock(spec=PushLogStore),
        openrouter_client=client,
        scheduler=make_workflow_scheduler(),
        settings=make_settings(),
    )
    await svc.sync(fake_creds)

    client.complete.assert_not_awaited()
    notifier.push.assert_not_awaited()


# ── fire_reminder ─────────────────────────────────────────────────────────────

async def test_fire_reminder_pushes_and_logs():
    rid = uuid4()
    store = MagicMock(spec=CalendarReminderStore)
    store.mark_sent = AsyncMock(return_value="Meeting in 1 hour")
    push_log = MagicMock(spec=PushLogStore)
    push_log.log = AsyncMock()
    notifier = make_notifier()

    svc, _ = make_reminder_service(notifier=notifier)
    svc._store = store
    svc._push_log = push_log
    await svc.fire_reminder(rid)

    notifier.push.assert_awaited_once_with("Meeting in 1 hour")
    push_log.log.assert_awaited_once()


async def test_fire_reminder_noop_when_already_sent_or_missing():
    rid = uuid4()
    store = MagicMock(spec=CalendarReminderStore)
    store.mark_sent = AsyncMock(return_value=None)
    push_log = MagicMock(spec=PushLogStore)
    push_log.log = AsyncMock()
    notifier = make_notifier()

    svc, _ = make_reminder_service(notifier=notifier)
    svc._store = store
    svc._push_log = push_log
    await svc.fire_reminder(rid)

    notifier.push.assert_not_awaited()
    push_log.log.assert_not_awaited()


# ── replay_unsent ─────────────────────────────────────────────────────────────

async def test_start_replays_unsent_reminders():
    from ze_calendar.reminders.calendar_store import CalendarReminder
    fire_at = _future(minutes=60)
    reminders = [
        CalendarReminder(id=uuid4(), event_id="e1", event_title="A", fire_at=fire_at,
                         label="Reminder A", sent=False, assessed_at=fire_at),
        CalendarReminder(id=uuid4(), event_id="e2", event_title="B", fire_at=fire_at,
                         label="Reminder B", sent=False, assessed_at=fire_at),
    ]
    store = MagicMock(spec=CalendarReminderStore)
    store.list_unsent = AsyncMock(return_value=reminders)
    sched = make_workflow_scheduler()

    svc, _ = make_reminder_service()
    svc._store = store
    svc._scheduler = sched
    await svc.replay_unsent()

    assert sched.schedule_at.call_count == 2


# ── WorkflowScheduler failure alerts ─────────────────────────────────────────

def make_workflow(name="test_wf"):
    wf = MagicMock(spec=Workflow)
    wf.id = uuid4()
    wf.name = name
    return wf


def make_failure_handler(settings=None, push_log=None, notifier=None):
    """Build the same on_failure closure the container wires into WorkflowScheduler."""
    _settings = settings or make_settings()
    _push_log = push_log or MagicMock(spec=PushLogStore)
    _notifier = notifier or make_notifier()

    async def on_failure(workflow, exc):
        alerts_cfg = _settings.proactive_config.get("alerts", {})
        if not alerts_cfg.get("workflow_failure_enabled", True):
            return
        cooldown = int(alerts_cfg.get("workflow_failure_cooldown_hours", 1))
        event_type = f"workflow_failure:{workflow.id}"
        if await _push_log.was_sent_within_hours(event_type, cooldown):
            return
        await _notifier.push(
            f"Workflow failed: *{workflow.name}*\n`{str(exc)[:200]}`",
            format="markdown",
            urgency="high",
        )
        await _push_log.log(event_type, workflow.name)

    return on_failure


async def test_workflow_failure_alert_fires():
    push_log = MagicMock(spec=PushLogStore)
    push_log.was_sent_within_hours = AsyncMock(return_value=False)
    push_log.log = AsyncMock()
    notifier = make_notifier()
    handler = make_failure_handler(push_log=push_log, notifier=notifier)

    wf = make_workflow("my_workflow")
    await handler(wf, Exception("boom"))

    notifier.push.assert_awaited_once()
    msg = notifier.push.call_args[0][0]
    assert "my_workflow" in msg


async def test_workflow_failure_alert_respects_cooldown():
    push_log = MagicMock(spec=PushLogStore)
    push_log.was_sent_within_hours = AsyncMock(return_value=True)
    notifier = make_notifier()
    handler = make_failure_handler(push_log=push_log, notifier=notifier)

    await handler(make_workflow(), Exception("boom"))
    notifier.push.assert_not_awaited()


async def test_workflow_failure_alert_disabled():
    import yaml
    import tempfile, pathlib as pl
    tmp = pl.Path(tempfile.mkdtemp())
    real_cfg = pl.Path(__file__).parent.parent.parent / "config" / "config.yaml"
    cfg = yaml.safe_load(real_cfg.read_text())
    cfg.setdefault("proactive", {}).setdefault("alerts", {})["workflow_failure_enabled"] = False
    (tmp / "config.yaml").write_text(yaml.dump(cfg))
    get_settings.cache_clear()
    settings = Settings(
        openrouter_api_key="k",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=tmp,
    )

    notifier = make_notifier()
    handler = make_failure_handler(settings=settings, notifier=notifier)
    await handler(make_workflow(), Exception("boom"))
    notifier.push.assert_not_awaited()


# ── schedule_at ───────────────────────────────────────────────────────────────

def test_schedule_at_uses_date_trigger():
    from apscheduler.triggers.date import DateTrigger

    ws = WorkflowScheduler(
        workflow_store=MagicMock(),
        executor=AsyncMock(),
    )
    ws._scheduler = MagicMock()
    fire_at = _future(minutes=30)
    ws.schedule_at(fn=lambda: None, dt=fire_at, job_id="test_job")

    ws._scheduler.add_job.assert_called_once()
    trigger = ws._scheduler.add_job.call_args[1].get("trigger") or ws._scheduler.add_job.call_args[0][1]
    assert isinstance(trigger, DateTrigger)
