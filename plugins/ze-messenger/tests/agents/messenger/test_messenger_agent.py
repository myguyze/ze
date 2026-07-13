from unittest.mock import AsyncMock, MagicMock


from ze_agents.settings import Settings
from ze_agents.types import AgentContext, AgentResult
from ze_communication.registry import ChannelRegistry
from ze_messenger.agents.messenger.agent import MessengerAgent
from ze_sdk.memory import MemoryContext


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_client(loop_response: str = "Your inbox is empty.") -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(loop_response, None))
    client.complete = AsyncMock(return_value="ok")

    async def _stream(*args, **kwargs):
        for token in loop_response.split():
            yield token

    client.stream = _stream
    return client


def make_creds(messages=None):
    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": messages or []
    }
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "ze@example.com"
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "msg1",
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 25 May 2026 10:00:00 +0000"}],
            "parts": [],
        },
    }
    creds = MagicMock()
    creds.gmail.return_value = service
    return creds


def make_gmail_channel(creds=None):
    from ze_google.gmail_channel import GmailChannel

    ch = GmailChannel(credentials=creds or make_creds())
    ch._user_email = "ze@example.com"
    return ch


def make_registry(channel=None):
    ch = channel or make_gmail_channel()
    return ChannelRegistry(channels=[ch])


def make_user_channel_store():
    store = AsyncMock()
    store.get_default_outbound = AsyncMock(return_value=None)
    store.list_all = AsyncMock(return_value=[])
    store.get = AsyncMock(return_value=None)
    return store


def make_thread_channel_map():
    m = AsyncMock()
    m.get = AsyncMock(return_value=None)
    m.set = AsyncMock()
    return m


def make_ctx(prompt: str = "check my inbox") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(client=None, registry=None) -> MessengerAgent:
    return MessengerAgent(
        openrouter_client=client or make_client(),
        channel_registry=registry or make_registry(),
        user_channel_store=make_user_channel_store(),
        thread_channel_map=make_thread_channel_map(),
        settings=make_settings(),
    )


# ── Registry ──────────────────────────────────────────────────────────────────


def test_messenger_agent_is_registered():
    from ze_agents.registry import _registry

    assert "messenger" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────


async def test_run_returns_agent_result():
    result = await make_agent().run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "messenger"


async def test_run_returns_response_from_agentic_loop():
    client = make_client("You have 3 unread messages.")
    result = await make_agent(client=client).run(make_ctx())
    assert result.response == "You have 3 unread messages."


# ── run() — agentic loop round-trips ─────────────────────────────────────────


async def test_run_lists_emails_when_llm_requests():
    """LLM calls list_emails once then returns text."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(
        side_effect=[
            (
                None,
                [
                    {
                        "id": "c1",
                        "name": "list_emails",
                        "arguments": {"query": "is:unread"},
                    }
                ],
            ),
            ("You have 2 unread emails.", None),
        ]
    )
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}, {"id": "m2"}]
    }
    creds = make_creds()
    creds.gmail.return_value = service

    registry = make_registry(make_gmail_channel(creds))
    result = await make_agent(client=client, registry=registry).run(make_ctx())

    assert result.response == "You have 2 unread emails."
    list_calls = [tc for tc in result.tool_calls if tc.tool_name == "list_emails"]
    assert len(list_calls) == 1


async def test_run_list_then_get_in_single_turn():
    """LLM lists emails to find ID, then fetches full content — two tool rounds."""
    import ze_messenger.agents.messenger.tools  # noqa

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(
        side_effect=[
            (
                None,
                [
                    {
                        "id": "c1",
                        "name": "list_emails",
                        "arguments": {"query": "from:boss"},
                    }
                ],
            ),
            (
                None,
                [{"id": "c2", "name": "get_email", "arguments": {"message_id": "m1"}}],
            ),
            ("Your boss sent you a meeting invite.", None),
        ]
    )
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
        "messages": [{"id": "m1"}]
    }
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
    creds = make_creds()
    creds.gmail.return_value = service

    registry = make_registry(make_gmail_channel(creds))
    result = await make_agent(client=client, registry=registry).run(
        make_ctx("read email from boss")
    )

    assert "boss" in result.response.lower() or "meeting" in result.response.lower()
    assert len([tc for tc in result.tool_calls if tc.tool_name == "list_emails"]) == 1
    assert len([tc for tc in result.tool_calls if tc.tool_name == "get_email"]) == 1


async def test_run_sends_email_when_llm_requests():
    """LLM calls send_email — routes through channel registry."""
    import ze_messenger.agents.messenger.tools  # noqa

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(
        side_effect=[
            (
                None,
                [
                    {
                        "id": "c1",
                        "name": "send_email",
                        "arguments": {
                            "to": "alice@example.com",
                            "subject": "Hi",
                            "body": "Hello!",
                        },
                    }
                ],
            ),
            ("Email sent to Alice.", None),
        ]
    )
    client.complete = AsyncMock(return_value="[]")

    service = MagicMock()
    service.users.return_value.messages.return_value.send.return_value.execute.return_value = {
        "id": "sent1",
        "threadId": "thread1",
    }
    service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "sent1",
        "payload": {
            "headers": [{"name": "Date", "value": "Mon, 25 May 2026 10:00:00 +0000"}],
            "parts": [],
        },
    }
    service.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "ze@example.com"
    }
    creds = make_creds()
    creds.gmail.return_value = service

    registry = make_registry(make_gmail_channel(creds))

    ctx = AgentContext(
        session_id="s1",
        prompt="send hi to alice",
        intent="create",
        memory=MemoryContext(),
        messages=[{"role": "user", "content": "send hi to alice"}],
    )
    result = await make_agent(client=client, registry=registry).run(ctx)

    assert "sent" in result.response.lower() or "alice" in result.response.lower()
    send_calls = [tc for tc in result.tool_calls if tc.tool_name == "send_email"]
    assert len(send_calls) == 1


async def test_run_no_tool_calls_when_llm_answers_directly():
    result = await make_agent().run(make_ctx())
    email_calls = list(result.tool_calls)
    assert len(email_calls) == 0


async def test_run_handles_list_emails_failure_gracefully():
    import ze_messenger.agents.messenger.tools  # noqa

    service = MagicMock()
    service.users.return_value.messages.return_value.list.return_value.execute.side_effect = Exception(
        "Gmail API error"
    )
    creds = make_creds()
    creds.gmail.return_value = service

    client = AsyncMock()
    client.complete_with_tools = AsyncMock(
        side_effect=[
            (None, [{"id": "c1", "name": "list_emails", "arguments": {}}]),
            ("I couldn't fetch your emails right now.", None),
        ]
    )
    client.complete = AsyncMock(return_value="[]")

    registry = make_registry(make_gmail_channel(creds))
    result = await make_agent(client=client, registry=registry).run(make_ctx())
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
