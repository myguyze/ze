import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_calendar.agents.calendar.agent import CalendarAgent
from ze_agents.types import AgentContext, AgentResult
from ze_api.logging import configure_logging
from ze_memory.types import MemoryContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    from ze_api.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
        timezone="Europe/Lisbon",
    )


def make_client(loop_response: str = "You have no upcoming events.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(loop_response, None))
    client.complete = AsyncMock(return_value="ok")

    async def _stream(*args, **kwargs):
        for token in loop_response.split():
            yield token

    client.stream = _stream
    return client


def make_credentials(events: list | None = None) -> MagicMock:
    service = MagicMock()
    (
        service.events.return_value
             .list.return_value
             .execute.return_value
    ) = {"items": events or []}

    creds = MagicMock()
    creds.calendar.return_value = service
    return creds


def make_ctx(prompt: str = "what do I have today?") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(client=None, creds=None) -> CalendarAgent:
    return CalendarAgent(
        openrouter_client=client or make_client(),
        google_credentials=creds or make_credentials(),
        settings=make_settings(),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registry ──────────────────────────────────────────────────────────────────

def test_calendar_agent_is_registered():
    from ze_agents.registry import _registry
    assert "calendar" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "calendar"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("You have a dentist at 10am.")
    result = await make_agent(client=client).run(make_ctx())
    assert result.response == "You have a dentist at 10am."


# ── run() — agentic loop round-trips ─────────────────────────────────────────

async def test_run_lists_events_when_llm_requests():
    """LLM calls list_events once then returns text."""
    import ze_calendar.agents.calendar.tools  # noqa: ensure calendar tools registered

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_events", "arguments": {"query": "today"}}]),
        ("You have a dentist appointment.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    creds = make_credentials(events=[{"summary": "Dentist", "start": {"dateTime": "2026-05-23T10:00:00"}}])
    result = await make_agent(client=client, creds=creds).run(make_ctx())

    assert result.response == "You have a dentist appointment."
    list_calls = [tc for tc in result.tool_calls if tc.tool_name == "list_events"]
    assert len(list_calls) == 1


async def test_run_creates_event_when_llm_requests():
    """LLM calls create_event directly (capability gate handles confirmation)."""
    import ze_calendar.agents.calendar.tools  # noqa

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "create_event", "arguments": {
            "summary": "Team standup",
            "start": "2026-05-24T09:00:00+01:00",
            "end": "2026-05-24T09:30:00+01:00",
        }}]),
        ("Created: Team standup on 24 May at 9am.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.events.return_value.insert.return_value.execute.return_value = {
        "id": "evt1", "htmlLink": "https://cal.google.com/e/evt1"
    }
    creds = MagicMock()
    creds.calendar.return_value = service

    ctx = AgentContext(
        session_id="s1", prompt="schedule standup", intent="create",
        memory=MemoryContext(), messages=[{"role": "user", "content": "schedule standup"}],
    )
    result = await make_agent(client=client, creds=creds).run(ctx)

    assert "Created" in result.response
    create_calls = [tc for tc in result.tool_calls if tc.tool_name == "create_event"]
    assert len(create_calls) == 1


async def test_run_list_then_update_in_single_turn():
    """LLM lists events to find ID, then updates — two tool-call rounds."""
    import ze_calendar.agents.calendar.tools  # noqa

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_events", "arguments": {"query": "standup"}}]),
        (None, [{"id": "c2", "name": "update_event", "arguments": {
            "event_id": "evt42", "start": "2026-05-24T10:00:00+01:00", "end": "2026-05-24T10:30:00+01:00",
        }}]),
        ("Moved standup to 10am.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.events.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "evt42", "summary": "Standup"}]
    }
    service.events.return_value.get.return_value.execute.return_value = {"id": "evt42", "summary": "Standup"}
    service.events.return_value.update.return_value.execute.return_value = {"id": "evt42", "htmlLink": "https://cal.google.com/e/evt42"}
    creds = MagicMock()
    creds.calendar.return_value = service

    result = await make_agent(client=client, creds=creds).run(make_ctx("move standup to 10am"))

    assert result.response == "Moved standup to 10am."
    assert len([tc for tc in result.tool_calls if tc.tool_name == "list_events"]) == 1
    assert len([tc for tc in result.tool_calls if tc.tool_name == "update_event"]) == 1


async def test_run_no_tool_calls_when_llm_answers_directly():
    """LLM responds without calling any tools."""
    result = await make_agent().run(make_ctx())  # make_client returns text immediately
    calendar_calls = list(result.tool_calls)
    assert len(calendar_calls) == 0


async def test_run_handles_list_events_failure_gracefully():
    """Failed list_events is passed to LLM; agent still returns response."""
    import ze_calendar.agents.calendar.tools  # noqa

    service = MagicMock()
    service.events.return_value.list.return_value.execute.side_effect = Exception("API error")
    creds = MagicMock()
    creds.calendar.return_value = service

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_events", "arguments": {}}]),
        ("I couldn't fetch your events right now.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    result = await make_agent(client=client, creds=creds).run(make_ctx())
    list_tc = next(tc for tc in result.tool_calls if tc.tool_name == "list_events")
    assert list_tc.success is False
    assert result.response


async def test_run_injects_timezone_into_system_prompt():
    captured: list[str] = []

    client = AsyncMock()
    async def _cwt(messages, model, tools, system=None, **kwargs):
        if system:
            captured.append(system)
        return ("ok", None)
    client.complete_with_tools = _cwt
    client.complete = AsyncMock(return_value="[]")

    await make_agent(client=client).run(make_ctx())
    assert captured and "Europe/Lisbon" in captured[0]


async def test_run_tool_call_has_duration():
    result = await make_agent().run(make_ctx())
    assert all(tc.duration_ms >= 0 for tc in result.tool_calls)


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens():
    client = make_client("Monday Tuesday Wednesday")
    tokens = [t async for t in make_agent(client=client).stream(make_ctx())]
    assert len(tokens) > 0
    assert "".join(tokens).strip() != ""
