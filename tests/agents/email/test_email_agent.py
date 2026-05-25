import pathlib
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze.agents.email.agent import EmailAgent
from ze.agents.types import AgentContext, AgentResult
from ze.logging import configure_logging
from ze.memory.types import MemoryContext


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


def make_client(loop_response: str = "Your inbox is empty.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(loop_response, None))
    client.complete = AsyncMock(return_value="[]")  # extract_facts

    async def _stream(*args, **kwargs):
        for token in loop_response.split():
            yield token

    client.stream = _stream
    return client


def make_credentials(messages: list | None = None) -> MagicMock:
    service = MagicMock()
    (
        service.users.return_value
             .messages.return_value
             .list.return_value
             .execute.return_value
    ) = {"messages": messages or []}
    # stub getProfile for EmailChannel._resolve_user_email
    (
        service.users.return_value
             .getProfile.return_value
             .execute.return_value
    ) = {"emailAddress": "ze@example.com"}
    # stub messages.get for EmailChannel.send timestamp fetch
    (
        service.users.return_value
             .messages.return_value
             .get.return_value
             .execute.return_value
    ) = {"id": "msg1", "payload": {"headers": [{"name": "Date", "value": "Mon, 25 May 2026 10:00:00 +0000"}], "parts": []}}

    creds = MagicMock()
    creds.gmail.return_value = service
    return creds


def make_ctx(prompt: str = "check my inbox") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(client=None, creds=None) -> EmailAgent:
    return EmailAgent(
        openrouter_client=client or make_client(),
        google_credentials=creds or make_credentials(),
        settings=make_settings(),
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registry ──────────────────────────────────────────────────────────────────

def test_email_agent_is_registered():
    from ze.agents.registry import _registry
    assert "email" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "email"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("You have 3 unread messages.")
    result = await make_agent(client=client).run(make_ctx())
    assert result.response == "You have 3 unread messages."


async def test_run_always_includes_extract_facts():
    result = await make_agent().run(make_ctx())
    assert result.tool_calls[-1].tool_name == "extract_facts"


# ── run() — agentic loop round-trips ─────────────────────────────────────────

async def test_run_lists_emails_when_llm_requests():
    """LLM calls list_emails once then returns text."""
    import ze.agents.email.tools  # noqa: ensure email tools registered

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_emails", "arguments": {"query": "is:unread"}}]),
        ("You have 2 unread emails.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}, {"id": "m2"}]
    }
    creds = MagicMock()
    creds.gmail.return_value = service

    result = await make_agent(client=client, creds=creds).run(make_ctx())

    assert result.response == "You have 2 unread emails."
    list_calls = [tc for tc in result.tool_calls if tc.tool_name == "list_emails"]
    assert len(list_calls) == 1


async def test_run_list_then_get_in_single_turn():
    """LLM lists emails to find ID, then fetches full content — two tool rounds."""
    import ze.agents.email.tools  # noqa

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_emails", "arguments": {"query": "from:boss"}}]),
        (None, [{"id": "c2", "name": "get_email", "arguments": {"message_id": "m1"}}]),
        ("Your boss sent you a meeting invite.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
    # get_email response
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "m1",
        "snippet": "Meeting tomorrow",
        "payload": {
            "headers": [
                {"name": "From", "value": "boss@example.com"},
                {"name": "Subject", "value": "Meeting"},
                {"name": "Date", "value": "Fri, 23 May 2026"},
            ],
            "mimeType": "text/plain",
            "body": {"data": ""},
        },
    }
    creds = MagicMock()
    creds.gmail.return_value = service

    result = await make_agent(client=client, creds=creds).run(make_ctx("read email from boss"))

    assert "boss" in result.response.lower() or "meeting" in result.response.lower()
    assert len([tc for tc in result.tool_calls if tc.tool_name == "list_emails"]) == 1
    assert len([tc for tc in result.tool_calls if tc.tool_name == "get_email"]) == 1


async def test_run_sends_email_when_llm_requests():
    """LLM calls send_email directly."""
    import ze.agents.email.tools  # noqa
    import base64
    from email.mime.text import MIMEText

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "send_email", "arguments": {
            "to": "alice@example.com", "subject": "Hi", "body": "Hello!",
        }}]),
        ("Email sent to Alice.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "sent1", "threadId": "thread1",
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "sent1",
        "payload": {"headers": [{"name": "Date", "value": "Mon, 25 May 2026 10:00:00 +0000"}], "parts": []},
    }
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "ze@example.com"
    }
    creds = MagicMock()
    creds.gmail.return_value = service

    ctx = AgentContext(
        session_id="s1", prompt="send hi to alice", intent="create",
        memory=MemoryContext(), messages=[{"role": "user", "content": "send hi to alice"}],
    )
    result = await make_agent(client=client, creds=creds).run(ctx)

    assert "sent" in result.response.lower() or "alice" in result.response.lower()
    send_calls = [tc for tc in result.tool_calls if tc.tool_name == "send_email"]
    assert len(send_calls) == 1


async def test_run_no_tool_calls_when_llm_answers_directly():
    result = await make_agent().run(make_ctx())
    email_calls = [tc for tc in result.tool_calls if tc.tool_name != "extract_facts"]
    assert len(email_calls) == 0


async def test_run_handles_list_emails_failure_gracefully():
    import ze.agents.email.tools  # noqa

    service = MagicMock()
    (
        service.users.return_value
             .messages.return_value
             .list.return_value
             .execute.side_effect
    ) = Exception("Gmail API error")
    creds = MagicMock()
    creds.gmail.return_value = service

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "list_emails", "arguments": {}}]),
        ("I couldn't fetch your emails right now.", None),
    ])
    client.complete = AsyncMock(return_value="[]")

    result = await make_agent(client=client, creds=creds).run(make_ctx())
    list_tc = next(tc for tc in result.tool_calls if tc.tool_name == "list_emails")
    assert list_tc.success is False
    assert result.response


async def test_run_tool_call_has_duration():
    result = await make_agent().run(make_ctx())
    assert all(tc.duration_ms >= 0 for tc in result.tool_calls)


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens():
    client = make_client("You have three unread messages.")
    tokens = [t async for t in make_agent(client=client).stream(make_ctx())]
    assert len(tokens) > 0
    assert "".join(tokens).strip() != ""
