from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from ze_news.agents.agent import NewsAgent, _format_candidates
from ze_news.agents.tools import get_headlines
from ze_news.types import Article, PersonalizationContext
from ze_agents.settings import Settings as CoreSettings
from ze_agents.types import AgentContext, AgentResult


def make_article(title: str = "AI breakthrough", url: str = "https://example.com/a1") -> Article:
    return Article(
        url=url,
        source_key="example",
        title=title,
        summary="Summary.",
        published_at=datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
        tags=["tech"],
    )


def make_ctx(prompt: str = "whats in the news regarding AI?") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        messages=[{"role": "user", "content": prompt}],
    )


def make_settings() -> CoreSettings:
    return CoreSettings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_agent(articles: list[Article] | None = None) -> NewsAgent:
    news_store = AsyncMock()
    news_store.search = AsyncMock(return_value=articles or [])
    agent = NewsAgent(
        client=AsyncMock(),
        memory_store=AsyncMock(),
        goal_provider=AsyncMock(),
        news_store=news_store,
        news_fetch_job=AsyncMock(),
        settings=make_settings(),
    )
    agent._preference_builder = AsyncMock()
    agent._preference_builder.build = AsyncMock(return_value=PersonalizationContext())
    return agent


async def test_run_prefetches_candidates_into_system_prompt():
    agent = make_agent([make_article()])
    captured: dict = {}

    async def fake_loop(ctx, *, client, messages, system, deps, **kwargs):
        captured["system"] = system
        return "Here are the headlines.", []

    with patch.object(agent, "agentic_loop", side_effect=fake_loop):
        result = await agent.run(make_ctx())

    assert isinstance(result, AgentResult)
    assert "AI breakthrough" in captured["system"]
    assert "https://example.com/a1" in captured["system"]
    assert "published: 2026-06-11" in captured["system"]
    agent._news_store.search.assert_awaited_once()


async def test_run_with_empty_store_marks_candidates_empty():
    agent = make_agent([])
    captured: dict = {}

    async def fake_loop(ctx, *, client, messages, system, deps, **kwargs):
        captured["system"] = system
        return "The local store has nothing on that.", []

    with patch.object(agent, "agentic_loop", side_effect=fake_loop):
        await agent.run(make_ctx())

    assert "(none — the local store returned no articles for this query)" in captured["system"]


async def test_run_records_prefetch_provenance_tool_call():
    agent = make_agent([make_article(url="https://example.com/a1")])

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("Done.", []))):
        result = await agent.run(make_ctx())

    assert result.tool_calls, "prefetch provenance must be recorded"
    provenance = result.tool_calls[0]
    assert provenance.tool_name == "search_news"
    assert provenance.args["prefetched"] is True
    assert provenance.result == ["https://example.com/a1"]


async def test_run_survives_store_failure():
    agent = make_agent()
    agent._news_store.search = AsyncMock(side_effect=RuntimeError("db down"))

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("No articles available.", []))):
        result = await agent.run(make_ctx())

    assert result.response == "No articles available."


def test_format_candidates_includes_source_date_url():
    text = _format_candidates([make_article()])
    assert "AI breakthrough" in text
    assert "source: example" in text
    assert "2026-06-11" in text
    assert "https://example.com/a1" in text


async def test_run_diagnostic_query_sets_diagnostic_deps():
    agent = make_agent()
    captured: dict = {}

    async def fake_loop(ctx, *, client, messages, system, deps, **kwargs):
        captured["deps"] = deps
        captured["system"] = system
        return "Because of your stored preferences.", []

    with patch.object(agent, "agentic_loop", side_effect=fake_loop):
        await agent.run(make_ctx("why do you keep suggesting bananas?"))

    assert captured["deps"]["_diagnostic_query"] is True
    system = " ".join(captured["system"].split())
    assert "diagnostics or preference management" in system


async def test_get_headlines_skips_for_diagnostic_query():
    news_store = AsyncMock()
    result = await get_headlines(
        news_store=news_store,
        _personalization_ctx=PersonalizationContext(),
        _diagnostic_query=True,
    )

    assert result["relevant"] == []
    assert result["discovery"] == []
    assert "Diagnostic" in result["note"]
    news_store.get_personalized.assert_not_called()
