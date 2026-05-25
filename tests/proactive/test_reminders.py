import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze.proactive.notifier import ProactiveNotifier
from ze.proactive.reminders import (
    CalendarReminderScheduler,
    _human_offset,
    _parse_interval,
)
from ze.settings import Settings, get_settings
from ze.workflow.scheduler import WorkflowScheduler
from ze.workflow.types import Workflow


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


def make_reminder_scheduler(
    conn=None, notifier=None, client=None, credentials=None, settings=None
):
    pool, c = make_pool(conn)
    return CalendarReminderScheduler(
        notifier=notifier or make_notifier(),
        pool=pool,
        openrouter_client=client or AsyncMock(),
        workflow_scheduler=make_workflow_scheduler(),
        google_credentials=credentials,  # None by default
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
    rs, _ = make_reminder_scheduler(client=client)

    now = datetime.now(timezone.utc)
    event = _make_event(start_offset_hours=5)
    start_time = now + timedelta(hours=5)
    result = await rs._assess_intervals(event, start_time, now)

    assert len(result) == 2
    offsets = [td for td, _ in result]
    assert timedelta(hours=2) in offsets
    assert timedelta(minutes=30) in offsets


async def test_assess_intervals_fallback_on_haiku_error():
    client = AsyncMock()
    client.complete = AsyncMock(side_effect=Exception("API error"))
    rs, _ = make_reminder_scheduler(client=client)

    now = datetime.now(timezone.utc)
    event = _make_event(start_offset_hours=5)
    start_time = now + timedelta(hours=5)
    result = await rs._assess_intervals(event, start_time, now)

    # Falls back to ["1 hour"]
    assert len(result) == 1
    assert result[0][0] == timedelta(hours=1)


async def test_assess_intervals_discards_past():
    client = AsyncMock()
    # Event starts in 30 minutes; "1 hour" interval → fire_at = -30 min (past)
    client.complete = AsyncMock(return_value='{"intervals": ["1 hour"]}')
    rs, _ = make_reminder_scheduler(client=client)

    now = datetime.now(timezone.utc)
    start_time = now + timedelta(minutes=30)
    event = _make_event(start_offset_hours=0.5)
    result = await rs._assess_intervals(event, start_time, now)

    assert result == []


# ── sync ──────────────────────────────────────────────────────────────────────

async def test_sync_skips_when_no_credentials():
    rs, conn = make_reminder_scheduler(credentials=None)
    await rs.sync()
    conn.fetch.assert_not_awaited()
    conn.fetchrow.assert_not_awaited()


async def test_sync_schedules_new_event():
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=[])  # no existing reminders for event
    reminder_id = uuid4()
    conn.fetchrow = AsyncMock(return_value={"id": reminder_id})

    client = AsyncMock()
    client.complete = AsyncMock(return_value='{"intervals": ["1 hour"]}')
    notifier = make_notifier()

    fake_creds = MagicMock()
    service_mock = MagicMock()
    fake_creds.calendar = MagicMock(return_value=service_mock)
    event = _make_event(start_offset_hours=5)
    service_mock.events.return_value.list.return_value.execute.return_value = {
        "items": [event]
    }

    pool, _ = make_pool(conn)
    sched = make_workflow_scheduler()

    rs = CalendarReminderScheduler(
        notifier=notifier,
        pool=pool,
        openrouter_client=client,
        workflow_scheduler=sched,
        google_credentials=fake_creds,
        settings=make_settings(),
    )
    await rs.sync()

    sched.schedule_at.assert_called_once()
    notifier.push.assert_awaited_once()
    confirmation = notifier.push.call_args[0][0]
    assert "Reminders set" in confirmation


async def test_sync_skips_known_event():
    conn = make_conn()
    assessed_at = datetime.now(timezone.utc)
    # existing row — assessed after the event was last updated
    conn.fetch = AsyncMock(return_value=[{
        "id": uuid4(),
        "assessed_at": assessed_at + timedelta(hours=1),  # assessed AFTER event update
        "sent": False,
    }])

    client = AsyncMock()
    notifier = make_notifier()

    fake_creds = MagicMock()
    service_mock = MagicMock()
    fake_creds.calendar = MagicMock(return_value=service_mock)
    event = _make_event(start_offset_hours=5, updated_offset_hours=-2)
    service_mock.events.return_value.list.return_value.execute.return_value = {"items": [event]}

    pool, _ = make_pool(conn)
    rs = CalendarReminderScheduler(
        notifier=notifier,
        pool=pool,
        openrouter_client=client,
        workflow_scheduler=make_workflow_scheduler(),
        google_credentials=fake_creds,
        settings=make_settings(),
    )
    await rs.sync()

    # Event already known and not rescheduled — no LLM call, no push
    client.complete.assert_not_awaited()
    notifier.push.assert_not_awaited()


# ── fire_reminder ─────────────────────────────────────────────────────────────

async def test_fire_reminder_pushes_and_logs():
    rid = uuid4()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={"label": "Meeting in 1 hour"})
    notifier = make_notifier()

    rs, _ = make_reminder_scheduler(conn=conn, notifier=notifier)
    await rs.fire_reminder(rid)

    notifier.push.assert_awaited_once_with("Meeting in 1 hour")
    conn.execute.assert_awaited_once()  # INSERT push_log


async def test_fire_reminder_noop_when_already_sent_or_missing():
    rid = uuid4()
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # UPDATE returned no row — already sent
    notifier = make_notifier()

    rs, _ = make_reminder_scheduler(conn=conn, notifier=notifier)
    await rs.fire_reminder(rid)

    notifier.push.assert_not_awaited()
    conn.execute.assert_not_awaited()


# ── start (replay) ────────────────────────────────────────────────────────────

async def test_start_replays_unsent_reminders():
    fire_at = _future(minutes=60)
    rows = [
        {"id": uuid4(), "fire_at": fire_at, "label": "Reminder A"},
        {"id": uuid4(), "fire_at": fire_at, "label": "Reminder B"},
    ]
    conn = make_conn()
    conn.fetch = AsyncMock(return_value=rows)

    pool, _ = make_pool(conn)
    sched = make_workflow_scheduler()

    rs = CalendarReminderScheduler(
        notifier=make_notifier(),
        pool=pool,
        openrouter_client=AsyncMock(),
        workflow_scheduler=sched,
        google_credentials=None,
        settings=make_settings(),
    )
    await rs.start()

    assert sched.schedule_at.call_count == 2


# ── WorkflowScheduler failure alerts ─────────────────────────────────────────

def make_workflow(name="test_wf"):
    wf = MagicMock(spec=Workflow)
    wf.id = uuid4()
    wf.name = name
    return wf


def make_scheduler_with_notifier(conn=None, notifier=None):
    pool, c = make_pool(conn)
    sched = MagicMock(spec=AsyncMock)  # mock the APScheduler internals
    ws = WorkflowScheduler(
        workflow_store=AsyncMock(),
        workflow_graph=AsyncMock(),
        graph_config={},
        settings=make_settings(),
        pool=pool,
        notifier=notifier or make_notifier(),
    )
    return ws, c


async def test_workflow_failure_alert_fires():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value=None)  # no cooldown row
    notifier = make_notifier()
    ws, _ = make_scheduler_with_notifier(conn=conn, notifier=notifier)

    wf = make_workflow("my_workflow")
    await ws._push_failure_alert(wf, Exception("boom"))

    notifier.push.assert_awaited_once()
    msg = notifier.push.call_args[0][0]
    assert "my_workflow" in msg


async def test_workflow_failure_alert_respects_cooldown():
    conn = make_conn()
    conn.fetchrow = AsyncMock(return_value={"1": 1})  # cooldown row found
    notifier = make_notifier()
    ws, _ = make_scheduler_with_notifier(conn=conn, notifier=notifier)

    await ws._push_failure_alert(make_workflow(), Exception("boom"))
    notifier.push.assert_not_awaited()


async def test_workflow_failure_alert_disabled():
    # Build settings where workflow_failure_alerts is false
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
    pool, _ = make_pool()
    ws = WorkflowScheduler(
        workflow_store=AsyncMock(),
        workflow_graph=AsyncMock(),
        graph_config={},
        settings=settings,
        pool=pool,
        notifier=notifier,
    )
    await ws._push_failure_alert(make_workflow(), Exception("boom"))
    notifier.push.assert_not_awaited()


# ── schedule_at ───────────────────────────────────────────────────────────────

def test_schedule_at_uses_date_trigger():
    from apscheduler.triggers.date import DateTrigger

    ws = WorkflowScheduler(
        workflow_store=MagicMock(),
        workflow_graph=MagicMock(),
        graph_config={},
        settings=make_settings(),
    )
    # Replace internal scheduler with a mock to capture the add_job call
    ws._scheduler = MagicMock()
    fire_at = _future(minutes=30)
    ws.schedule_at(fn=lambda: None, dt=fire_at, job_id="test_job")

    ws._scheduler.add_job.assert_called_once()
    trigger = ws._scheduler.add_job.call_args[1].get("trigger") or ws._scheduler.add_job.call_args[0][1]
    assert isinstance(trigger, DateTrigger)
