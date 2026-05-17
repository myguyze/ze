import pytest
from unittest.mock import AsyncMock

from ze.agents.research.agent import ResearchAgent
from ze.agents.research.tools import format_search_results
from ze.agents.types import AgentContext, AgentResult, ToolCall
from ze.logging import configure_logging
from ze.memory.types import MemoryContext, UserFact


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    import pathlib
    from ze.settings import Settings, get_settings
    get_settings.cache_clear()
    real_config = pathlib.Path(__file__).parent.parent.parent.parent / "config"
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
        database_url_sync="postgresql+psycopg2://ze:ze@localhost:5432/ze",
        config_dir=real_config,
    )


def make_client(response: str = "Here is what I found.") -> AsyncMock:
    client = AsyncMock()
    client.complete = AsyncMock(return_value=response)

    async def _stream(*args, **kwargs):
        for token in response.split():
            yield token

    client.stream = _stream
    return client


def make_tavily(result: dict | None = None) -> AsyncMock:
    tavily = AsyncMock()
    tavily.search = AsyncMock(return_value=result or {
        "results": [
            {"title": "AI News", "url": "https://example.com", "content": "Latest AI developments."}
        ]
    })
    return tavily


def make_ctx(prompt: str = "find AI news", memory: MemoryContext | None = None) -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=memory or MemoryContext(),
    )


def make_agent(client=None, tavily=None) -> ResearchAgent:
    settings = make_settings()
    return ResearchAgent(
        openrouter_client=client or make_client(),
        tavily_client=tavily or make_tavily(),
        settings=settings,
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registry ──────────────────────────────────────────────────────────────────

def test_research_agent_is_registered():
    from ze.agents.registry import _registry
    assert "research" in _registry


# ── run() ─────────────────────────────────────────────────────────────────────

async def test_run_returns_agent_result():
    agent = make_agent()
    result = await agent.run(make_ctx())
    assert isinstance(result, AgentResult)
    assert result.agent == "research"


async def test_run_returns_response_string():
    client = make_client("Here is the latest AI news.")
    agent = make_agent(client=client)
    result = await agent.run(make_ctx("find AI news"))
    assert result.response == "Here is the latest AI news."


async def test_run_includes_tool_calls():
    agent = make_agent()
    result = await agent.run(make_ctx())
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "web_search"


async def test_run_calls_tavily_with_prompt():
    tavily = make_tavily()
    agent = make_agent(tavily=tavily)
    await agent.run(make_ctx("quantum computing news"))
    tavily.search.assert_awaited_once()
    call_args = tavily.search.call_args
    assert "quantum computing news" in call_args.args or "quantum computing news" in str(call_args)


async def test_run_augments_prompt_with_search_results():
    tavily = make_tavily({
        "results": [{"title": "Test", "url": "https://t.co", "content": "unique_content_xyz"}]
    })
    captured_messages = []

    client = AsyncMock()
    async def _complete(messages, **kwargs):
        captured_messages.extend(messages)
        return "done"
    client.complete = _complete

    agent = make_agent(client=client, tavily=tavily)
    await agent.run(make_ctx("test query"))

    user_message = captured_messages[0]["content"]
    assert "unique_content_xyz" in user_message


async def test_run_with_memory_facts_injects_into_system_prompt():
    memory = MemoryContext(facts=[UserFact(key="name", value="Alice")])
    captured_system: list[str] = []

    client = AsyncMock()
    async def _complete(messages, system=None, **kwargs):
        if system:
            captured_system.append(system)
        return "done"
    client.complete = _complete

    agent = make_agent(client=client)
    await agent.run(make_ctx(memory=memory))

    assert captured_system
    assert "name: Alice" in captured_system[0]


async def test_run_handles_tavily_failure_gracefully():
    tavily = AsyncMock()
    tavily.search = AsyncMock(side_effect=Exception("Tavily down"))
    client = make_client("I could not find anything.")
    agent = make_agent(client=client, tavily=tavily)
    # Should not raise — failed search is included as a failed ToolCall
    result = await agent.run(make_ctx())
    assert result.tool_calls[0].success is False
    assert result.response == "I could not find anything."


async def test_run_tool_call_has_duration():
    agent = make_agent()
    result = await agent.run(make_ctx())
    assert result.tool_calls[0].duration_ms >= 0


# ── stream() ─────────────────────────────────────────────────────────────────

async def test_stream_yields_tokens():
    client = make_client("hello world")
    agent = make_agent(client=client)
    tokens = [t async for t in agent.stream(make_ctx())]
    assert len(tokens) > 0
    assert "".join(tokens).strip() != ""


# ── format_search_results ─────────────────────────────────────────────────────

def test_format_search_results_success():
    tc = ToolCall(
        tool_name="web_search",
        args={},
        result={"results": [{"title": "T", "url": "https://u.co", "content": "body"}]},
        duration_ms=10,
        success=True,
    )
    text = format_search_results(tc)
    assert "body" in text
    assert "https://u.co" in text


def test_format_search_results_failed_tool_call():
    tc = ToolCall(
        tool_name="web_search",
        args={},
        result=None,
        duration_ms=5,
        success=False,
        error="timeout",
    )
    text = format_search_results(tc)
    assert "search failed" in text


def test_format_search_results_empty_results():
    tc = ToolCall(
        tool_name="web_search",
        args={},
        result={"results": []},
        duration_ms=5,
        success=True,
    )
    text = format_search_results(tc)
    assert "no search results" in text
