import json
import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.agents.reminders.agent import RemindersAgent, _human_delta
from ze.agents.types import AgentContext
from ze.capability.types import GateDecision
from ze.memory.types import MemoryContext
from ze.settings import Settings


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings() -> Settings:
    from ze.settings import get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_agent(llm_response: str) -> tuple[RemindersAgent, MagicMock, MagicMock, MagicMock]:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=llm_response)

    store = AsyncMock()
    scheduler = MagicMock()
    notifier = AsyncMock()

    agent = RemindersAgent(
        openrouter_client=client,
        reminder_store=store,
        workflow_scheduler=scheduler,
        notifier=notifier,
        settings=make_settings(),
    )
    return agent, store, scheduler, notifier


def make_ctx(prompt: str = "remind me in 1 hour") -> AgentContext:
    return AgentContext(
        session_id="test",
        prompt=prompt,
        intent="manage",
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _future(hours: int = 2) -> datetime:
    return _now() + timedelta(hours=hours)


# ── _human_delta ──────────────────────────────────────────────────────────────

def test_human_delta_minutes():
    assert _human_delta(timedelta(minutes=30)) == "in 30 minutes"


def test_human_delta_hours():
    assert _human_delta(timedelta(hours=2)) == "in 2 hours"


def test_human_delta_hours_and_minutes():
    assert _human_delta(timedelta(hours=1, minutes=30)) == "in 1 hour 30 minutes"


def test_human_delta_days():
    assert _human_delta(timedelta(days=3)) == "in 3 days"


def test_human_delta_one_day():
    assert _human_delta(timedelta(days=1)) == "in 1 day"


# ── set action ────────────────────────────────────────────────────────────────

async def test_set_creates_reminder_and_schedules():
    rid = uuid4()
    payload = json.dumps({"action": "set", "label": "Take medication", "fire_at": _future().isoformat(), "cancel_hint": None})
    agent, store, scheduler, _ = make_agent(payload)
    store.create = AsyncMock(return_value=rid)

    result = await agent.run(make_ctx())

    store.create.assert_called_once()
    scheduler.schedule_at.assert_called_once()
    assert "Take medication" in result.response
    assert "⏰" in result.response


async def test_set_rejects_past_time():
    past = datetime(2020, 1, 1, tzinfo=timezone.utc)
    payload = json.dumps({"action": "set", "label": "Old thing", "fire_at": past.isoformat(), "cancel_hint": None})
    agent, store, scheduler, _ = make_agent(payload)

    result = await agent.run(make_ctx())

    store.create.assert_not_called()
    assert "past" in result.response


async def test_set_missing_fire_at():
    payload = json.dumps({"action": "set", "label": "Something", "fire_at": None, "cancel_hint": None})
    agent, store, _, _ = make_agent(payload)

    result = await agent.run(make_ctx())

    store.create.assert_not_called()
    assert "time" in result.response.lower()


async def test_set_bad_json_returns_fallback():
    agent, store, _, _ = make_agent("not json at all")

    result = await agent.run(make_ctx())

    store.create.assert_not_called()
    assert "couldn't understand" in result.response.lower()


# ── list action ───────────────────────────────────────────────────────────────

async def test_list_no_pending():
    payload = json.dumps({"action": "list", "label": None, "fire_at": None, "cancel_hint": None})
    agent, store, _, _ = make_agent(payload)
    store.list_pending = AsyncMock(return_value=[])

    result = await agent.run(make_ctx("list my reminders"))

    assert "no pending" in result.response.lower()


async def test_list_shows_pending():
    from ze.reminders.store import Reminder
    payload = json.dumps({"action": "list", "label": None, "fire_at": None, "cancel_hint": None})
    agent, store, _, _ = make_agent(payload)
    store.list_pending = AsyncMock(return_value=[
        Reminder(id=uuid4(), label="Call João", fire_at=_future(), created_at=_now(), sent=False, sent_at=None),
    ])

    result = await agent.run(make_ctx("list my reminders"))

    assert "Call João" in result.response
    assert "⏰" in result.response


# ── cancel action ─────────────────────────────────────────────────────────────

async def test_cancel_no_pending():
    payload = json.dumps({"action": "cancel", "label": None, "fire_at": None, "cancel_hint": "medication"})
    agent, store, _, _ = make_agent(payload)
    store.list_pending = AsyncMock(return_value=[])

    result = await agent.run(make_ctx("cancel my reminder"))

    assert "no pending" in result.response.lower()


async def test_cancel_match_found():
    from ze.reminders.store import Reminder
    rid = uuid4()
    payload = json.dumps({"action": "cancel", "label": None, "fire_at": None, "cancel_hint": "medication"})
    agent, store, scheduler, _ = make_agent(payload)
    store.list_pending = AsyncMock(return_value=[
        Reminder(id=rid, label="Take medication", fire_at=_future(), created_at=_now(), sent=False, sent_at=None),
    ])
    store.delete = AsyncMock()

    result = await agent.run(make_ctx("cancel my medication reminder"))

    store.delete.assert_called_once_with(rid)
    scheduler.remove_job_if_exists.assert_called_once_with(f"user_reminder:{rid}")
    assert "✅" in result.response
    assert "Take medication" in result.response


async def test_cancel_no_match_lists_all():
    from ze.reminders.store import Reminder
    payload = json.dumps({"action": "cancel", "label": None, "fire_at": None, "cancel_hint": "xyz"})
    agent, store, _, _ = make_agent(payload)
    store.list_pending = AsyncMock(return_value=[
        Reminder(id=uuid4(), label="Call João", fire_at=_future(), created_at=_now(), sent=False, sent_at=None),
    ])

    result = await agent.run(make_ctx("cancel my xyz reminder"))

    assert "Call João" in result.response
    assert "couldn't find" in result.response.lower()
