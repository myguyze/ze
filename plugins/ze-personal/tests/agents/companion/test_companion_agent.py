from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_personal.agents.companion.agent import CompanionAgent, _detect_outreach_event
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.settings import Settings
from ze_memory.types import MemoryContext, Fact


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_client(response: str = "I'm here to help.") -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)

    async def _stream(*args, **kwargs):
        for token in response.split():
            yield token

    client.stream = _stream
    return client


def make_ctx(prompt: str = "how are you?", memory: MemoryContext | None = None) -> AgentContext:
    from ze_personal.persona.identity import build_identity_block
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="reason",
        memory=memory or MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
        identity_builder=build_identity_block,
    )


def make_pool():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


def make_person_store():
    store = AsyncMock()
    store.get_by_name = AsyncMock(return_value=[])
    return store


def make_agent(client=None) -> CompanionAgent:
    return CompanionAgent(
        openrouter_client=client or make_client(),
        settings=make_settings(),
        person_store=make_person_store(),
        pool=make_pool(),
    )


# ── Registry ──────────────────────────────────────────────────────────────────

def test_companion_agent_is_registered():
    from ze_core.orchestration.registry import _registry
    assert "companion" in _registry


# ── run() ─────────────────────────────────────────────────────────────────────

async def test_run_returns_agent_result():
    agent = make_agent()
    result = await agent.run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "companion"


async def test_run_returns_response_string():
    client = make_client("I am doing great, thank you!")
    agent = make_agent(client=client)
    result = await agent.run(make_ctx())
    assert result.response == "I am doing great, thank you!"


async def test_run_no_outreach_in_prompt_returns_no_tool_calls():
    agent = make_agent()
    result = await agent.run(make_ctx("how are you?"))
    assert result.tool_calls == []


async def test_run_outreach_for_non_prospect_returns_no_tool_calls():
    # person_store returns no match → tool returns "not a prospect" (success=False)
    # tool_calls list should still be empty (failed silent attempts are dropped)
    agent = make_agent()
    result = await agent.run(make_ctx("I sent an email to Carlos and he didn't reply"))
    assert result.tool_calls == []


async def test_run_sends_prompt_as_user_message():
    captured: list[list] = []

    client = AsyncMock()
    async def _complete(messages, **kwargs):
        captured.append(messages)
        return "ok"
    client.complete = _complete

    agent = make_agent(client=client)
    await agent.run(make_ctx("tell me a story"))

    assert captured[0][0]["role"] == "user"
    assert captured[0][0]["content"] == "tell me a story"


async def test_run_injects_memory_facts_into_system_prompt():
    memory = MemoryContext(facts=[Fact(predicate="name", value="João")])
    captured_system: list[str] = []

    client = AsyncMock()
    async def _complete(messages, system=None, **kwargs):
        if system:
            captured_system.append(system)
        return "ok"
    client.complete = _complete

    agent = make_agent(client=client)
    await agent.run(make_ctx(memory=memory))

    assert captured_system
    assert "name: João" in captured_system[0]


async def test_run_no_memory_shows_none_placeholder():
    captured_system: list[str] = []

    client = AsyncMock()
    async def _complete(messages, system=None, **kwargs):
        if system:
            captured_system.append(system)
        return "ok"
    client.complete = _complete

    agent = make_agent(client=client)
    await agent.run(make_ctx())

    assert "(none)" in captured_system[0]


async def test_run_uses_model_from_settings():
    captured_models: list[str] = []

    client = AsyncMock()
    async def _complete(messages, model=None, **kwargs):
        captured_models.append(model)
        return "ok"
    client.complete = _complete

    agent = make_agent(client=client)
    await agent.run(make_ctx())

    assert captured_models[0] is not None
    assert "claude" in captured_models[0]


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens():
    client = make_client("hello world friend")
    agent = make_agent(client=client)
    tokens = [t async for t in agent.stream(make_ctx())]
    assert len(tokens) > 0


async def test_stream_reconstructs_response():
    client = make_client("one two three")
    agent = make_agent(client=client)
    tokens = [t async for t in agent.stream(make_ctx())]
    assert " ".join(tokens) == "one two three"


# ── _detect_outreach_event ────────────────────────────────────────────────────

def test_detect_outreach_event_sent():
    result = _detect_outreach_event("I sent an email to Carlos Mendes yesterday")
    assert result is not None
    assert result["event_type"] == "sent"
    assert result["contact_name"] == "Carlos Mendes"
    assert result["channel"] == "email"


def test_detect_outreach_event_no_reply():
    result = _detect_outreach_event("João hasn't responded to my message")
    assert result is not None
    assert result["event_type"] == "no_reply"


def test_detect_outreach_event_no_match():
    assert _detect_outreach_event("how are you doing today?") is None


def test_detect_outreach_event_no_name():
    assert _detect_outreach_event("i sent an email yesterday") is None


# ── AgentContext ──────────────────────────────────────────────────────────────

def test_agent_context_defaults():
    ctx = AgentContext(session_id="x", prompt="hi", intent="reason")
    assert ctx.tool_calls == []
    assert ctx.memory is None
