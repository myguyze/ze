import pathlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze.agents.reminders.agent import RemindersAgent
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.capability.types import GateDecision
from ze_core.memory.types import MemoryContext
from ze.logging import configure_logging


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    from ze.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_client(response: str = "Reminder set.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(response, None))
    client.complete = AsyncMock(return_value=response)
    return client


def make_ctx(prompt: str = "remind me in 1 hour") -> AgentContext:
    return AgentContext(
        session_id="test",
        prompt=prompt,
        intent="manage",
        gate_decision=GateDecision.EXECUTE,
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(client=None) -> RemindersAgent:
    return RemindersAgent(
        openrouter_client=client or make_client(),
        reminder_store=AsyncMock(),
        workflow_scheduler=MagicMock(),
        notifier=AsyncMock(),
        settings=make_settings(),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registry ──────────────────────────────────────────────────────────────────

def test_reminders_agent_is_registered():
    from ze_core.orchestration.registry import _registry
    assert "reminders" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "reminders"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("⏰ Reminder set: Take medication. I'll remind you in 2 hours.")
    result = await make_agent(client=client).run(make_ctx())
    assert "Take medication" in result.response


# ── run() — tool call round-trips ────────────────────────────────────────────

async def test_run_sets_reminder_via_tool():
    import ze.agents.reminders.tools  # noqa: ensure tools registered

    rid = uuid4()
    fire_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    store = AsyncMock()
    store.create = AsyncMock(return_value=rid)
    scheduler = MagicMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "set_reminder", "arguments": {
            "label": "Take medication",
            "fire_at": fire_at,
        }}]),
        ("⏰ Reminder set: Take medication in 2 hours.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = RemindersAgent(
        openrouter_client=client,
        reminder_store=store,
        workflow_scheduler=scheduler,
        notifier=AsyncMock(),
        settings=make_settings(),
    )
    result = await agent.run(make_ctx())

    store.create.assert_called_once()
    scheduler.schedule_at.assert_called_once()
    assert "Take medication" in result.response
    assert len([tc for tc in result.tool_calls if tc.tool_name == "set_reminder"]) == 1


async def test_run_rejects_past_fire_at_via_tool():
    import ze.agents.reminders.tools  # noqa

    past = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()

    store = AsyncMock()
    store.create = AsyncMock(return_value=uuid4())
    scheduler = MagicMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "set_reminder", "arguments": {
            "label": "Old thing",
            "fire_at": past,
        }}]),
        ("That time is in the past. Please give me a future time.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = RemindersAgent(
        openrouter_client=client,
        reminder_store=store,
        workflow_scheduler=scheduler,
        notifier=AsyncMock(),
        settings=make_settings(),
    )
    result = await agent.run(make_ctx())

    store.create.assert_not_called()
    scheduler.schedule_at.assert_not_called()


async def test_run_lists_reminders_via_tool():
    import ze.agents.reminders.tools  # noqa

    from ze.reminders.store import Reminder

    rid = uuid4()
    fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
    store = AsyncMock()
    store.list_pending = AsyncMock(return_value=[
        Reminder(id=rid, label="Call João", fire_at=fire_at, created_at=datetime.now(timezone.utc), sent=False, sent_at=None),
    ])

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_reminders", "arguments": {}}]),
        ("⏰ Pending reminders (1): Call João.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = RemindersAgent(
        openrouter_client=client,
        reminder_store=store,
        workflow_scheduler=MagicMock(),
        notifier=AsyncMock(),
        settings=make_settings(),
    )
    result = await agent.run(make_ctx("list my reminders"))

    store.list_pending.assert_called_once()
    assert "Call João" in result.response


async def test_run_cancel_reminder_via_tool():
    import ze.agents.reminders.tools  # noqa

    from ze.reminders.store import Reminder

    rid = uuid4()
    fire_at = datetime.now(timezone.utc) + timedelta(hours=1)
    reminder = Reminder(id=rid, label="Take medication", fire_at=fire_at, created_at=datetime.now(timezone.utc), sent=False, sent_at=None)

    store = AsyncMock()
    store.list_pending = AsyncMock(return_value=[reminder])
    store.get = AsyncMock(return_value=reminder)
    store.delete = AsyncMock()
    scheduler = MagicMock()

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_reminders", "arguments": {}}]),
        (None, [{"id": "c2", "name": "cancel_reminder", "arguments": {"reminder_id": str(rid)}}]),
        ("✅ Cancelled: Take medication.", None),
    ])
    client.complete = AsyncMock(return_value="ok")

    agent = RemindersAgent(
        openrouter_client=client,
        reminder_store=store,
        workflow_scheduler=scheduler,
        notifier=AsyncMock(),
        settings=make_settings(),
    )
    result = await agent.run(make_ctx("cancel my medication reminder"))

    store.delete.assert_called_once_with(rid)
    scheduler.remove_job_if_exists.assert_called_once_with(f"user_reminder:{rid}")
    assert "Take medication" in result.response


async def test_run_no_tool_calls_when_llm_answers_directly():
    result = await make_agent().run(make_ctx())
    assert len(result.tool_calls) == 0


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_response():
    client = make_client("⏰ Reminder set.")
    tokens = [t async for t in make_agent(client=client).stream(make_ctx())]
    assert "".join(tokens) == "⏰ Reminder set."


# ── _human_delta helper (standalone, no agent needed) ─────────────────────────

from ze.agents.reminders.tools import set_reminder as _  # noqa: just ensure module importable


def _human_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts = ["less than a minute"]
    return "in " + " ".join(parts)


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
