import pytest
from unittest.mock import AsyncMock

from ze_personal.agents.research.agent import ResearchAgent
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.settings import Settings
from ze_memory.types import MemoryContext, Fact


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_client(
    loop_response: str = "Here is what I found.",
    facts_response: str = "[]",
) -> AsyncMock:
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(return_value=(loop_response, None))
    client.complete = AsyncMock(return_value=facts_response)

    async def _stream(*args, **kwargs):
        for token in loop_response.split():
            yield token

    client.stream = _stream
    return client


def make_ctx(prompt: str = "find AI news", memory: MemoryContext | None = None) -> AgentContext:
    from ze_personal.persona.identity import build_identity_block
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=memory or MemoryContext(),
        messages=[{"role": "user", "content": prompt}],
        identity_builder=build_identity_block,
    )


def make_agent(client=None) -> ResearchAgent:
    return ResearchAgent(
        openrouter_client=client or make_client(),
        settings=make_settings(),
    )


# ── Registry ──────────────────────────────────────────────────────────────────

def test_research_agent_is_registered():
    from ze_core.orchestration.registry import _registry
    assert "research" in _registry


# ── run() — basic structure ───────────────────────────────────────────────────

async def test_run_returns_agent_result():
    agent = make_agent()
    result = await agent.run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "research"


async def test_run_returns_response_from_agentic_loop():
    client = make_client(loop_response="Here is the latest AI news.")
    agent = make_agent(client=client)
    result = await agent.run(make_ctx("find AI news"))
    assert result.response == "Here is the latest AI news."


# ── run() — agentic loop with OpenRouter server tool round-trips ──────────────

async def test_run_single_search_iteration():
    """LLM requests one web_search (server tool) then returns text."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "openrouter:web_search", "arguments": {"query": "AI news"}}]),
        ("Here is what I found.", None),
    ])
    client.complete = AsyncMock(return_value="ok")
    agent = make_agent(client=client)

    result = await agent.run(make_ctx("AI news"))

    assert result.response == "Here is what I found."
    web_calls = [tc for tc in result.tool_calls if tc.tool_name == "openrouter:web_search"]
    assert len(web_calls) == 1
    assert web_calls[0].success is True


async def test_run_multiple_search_iterations():
    """LLM requests two searches before producing text."""
    client = AsyncMock()
    client.complete_with_tools = AsyncMock(side_effect=[
        (None, [{"id": "c1", "name": "openrouter:web_search", "arguments": {"query": "AI 2024"}}]),
        (None, [{"id": "c2", "name": "openrouter:web_search", "arguments": {"query": "AI 2025"}}]),
        ("Comprehensive answer.", None),
    ])
    client.complete = AsyncMock(return_value="[]")
    agent = make_agent(client=client)

    result = await agent.run(make_ctx("AI trends"))

    assert result.response == "Comprehensive answer."
    web_calls = [tc for tc in result.tool_calls if tc.tool_name == "openrouter:web_search"]
    assert len(web_calls) == 2


async def test_run_no_search_when_llm_answers_directly():
    """LLM returns text on first call — no web_search is recorded."""
    agent = make_agent()  # make_client returns text immediately
    result = await agent.run(make_ctx())
    web_calls = [tc for tc in result.tool_calls if tc.tool_name == "openrouter:web_search"]
    assert len(web_calls) == 0


async def test_run_with_memory_facts_injects_into_system_prompt():
    memory = MemoryContext(facts=[Fact(predicate="name", value="Alice")])
    captured: list[str] = []

    client = AsyncMock()
    async def _complete_with_tools(messages, model, tools, system=None, **kwargs):
        if system:
            captured.append(system)
        return ("done", None)
    client.complete_with_tools = _complete_with_tools
    client.complete = AsyncMock(return_value="[]")

    agent = make_agent(client=client)
    await agent.run(make_ctx(memory=memory))

    assert captured
    assert "name: Alice" in captured[0]


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens():
    client = make_client(loop_response="hello world")
    agent = make_agent(client=client)
    tokens = [t async for t in agent.stream(make_ctx())]
    assert len(tokens) > 0
    assert "".join(tokens).strip() != ""


async def test_stream_appends_online_suffix():
    """stream() appends :online to the model name so OpenRouter fetches web results."""
    captured_models: list[str] = []

    async def _stream(messages, model, system=None, **kwargs):
        captured_models.append(model)
        yield "token"

    client = AsyncMock()
    client.stream = _stream
    agent = make_agent(client=client)

    tokens = [t async for t in agent.stream(make_ctx())]

    assert tokens == ["token"]
    assert captured_models[0].endswith(":online")


async def test_stream_does_not_double_online_suffix():
    """If the model already ends in :online, it is not appended again."""
    from unittest.mock import patch

    captured_models: list[str] = []

    async def _stream(messages, model, system=None, **kwargs):
        captured_models.append(model)
        yield "token"

    client = AsyncMock()
    client.stream = _stream

    agent = make_agent(client=client)
    with patch.object(agent, "_model", return_value="anthropic/claude-sonnet-4-5:online"):
        [t async for t in agent.stream(make_ctx())]

    assert captured_models[0].count(":online") == 1
