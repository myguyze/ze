from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze_prospecting.agents.agent import ProspectingAgent
from ze_prospecting.types import ProspectingSettings
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.settings import Settings
from ze_personal.contacts.types import PersonContext
from ze_memory.types import MemoryContext


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_settings():
    return Settings(
        openrouter_api_key="test-key",
        database_url="postgresql://ze:ze@localhost:5432/ze",
    )


def make_campaign_store(campaign_id=None):
    store = AsyncMock()
    store.create = AsyncMock(return_value=campaign_id or uuid4())
    store.complete = AsyncMock()
    store.fail = AsyncMock()
    return store


def make_ctx(prompt: str = "find 5 charter operators in Portugal") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=MemoryContext(),
        contacts=PersonContext(),
        messages=[{"role": "user", "content": prompt}],
    )


def make_agent(
    client=None,
    browser_client=None,
    person_store=None,
    campaign_store=None,
) -> ProspectingAgent:
    if client is None:
        client = AsyncMock()
        client.complete = AsyncMock(return_value="Found 2 prospects.")
        client.complete_with_tools = AsyncMock(return_value=("Found 2 prospects.", None))
    if browser_client is None:
        browser_client = AsyncMock()
        browser_client.health = AsyncMock(return_value=True)
    if person_store is None:
        person_store = AsyncMock()
    return ProspectingAgent(
        openrouter_client=client,
        settings=make_settings(),
        prospecting_settings=ProspectingSettings(),
        browser_client=browser_client,
        person_store=person_store,
        campaign_store=campaign_store or make_campaign_store(),
    )


# ── Registration ──────────────────────────────────────────────────────────────

def test_prospecting_agent_is_registered():
    from ze_core.orchestration.registry import _registry
    assert "prospecting" in _registry


# ── run() ─────────────────────────────────────────────────────────────────────

async def test_prospecting_agent_run_creates_campaign():
    campaign_id = uuid4()
    cs = make_campaign_store(campaign_id)

    agent = make_agent(campaign_store=cs)

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("Found prospects.", []))):
        result = await agent.run(make_ctx())

    assert isinstance(result, AgentResult)
    assert result.agent == "prospecting"
    cs.create.assert_called_once_with("find 5 charter operators in Portugal")


async def test_prospecting_agent_run_sets_status_complete():
    campaign_id = uuid4()
    cs = make_campaign_store(campaign_id)

    agent = make_agent(campaign_store=cs)

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("Summary here.", []))):
        await agent.run(make_ctx())

    cs.complete.assert_called_once_with(campaign_id, "Summary here.")


async def test_prospecting_agent_failure_sets_status_failed():
    campaign_id = uuid4()
    cs = make_campaign_store(campaign_id)

    agent = make_agent(campaign_store=cs)

    with patch.object(agent, "agentic_loop", AsyncMock(side_effect=RuntimeError("LLM error"))):
        with pytest.raises(RuntimeError, match="LLM error"):
            await agent.run(make_ctx())

    cs.fail.assert_called_once_with(campaign_id)


async def test_prospecting_agent_browser_unreachable_excludes_browser_extract():
    browser_client = AsyncMock()
    browser_client.health = AsyncMock(return_value=False)

    captured_tool_names: list = []

    async def fake_agentic_loop(ctx, *, client, messages, system, deps, tool_names=None, **kwargs):
        captured_tool_names.extend(tool_names or [])
        return "Found prospects.", []

    agent = make_agent(browser_client=browser_client)

    with patch.object(agent, "agentic_loop", side_effect=fake_agentic_loop):
        await agent.run(make_ctx())

    assert "browser_extract" not in captured_tool_names
    assert "openrouter:web_search" in captured_tool_names


async def test_prospecting_agent_passes_campaign_id_in_deps():
    campaign_id = uuid4()
    cs = make_campaign_store(campaign_id)

    captured_deps: list[dict] = []

    async def fake_agentic_loop(ctx, *, client, messages, system, deps, **kwargs):
        captured_deps.append(deps)
        return "done", []

    agent = make_agent(campaign_store=cs)

    with patch.object(agent, "agentic_loop", side_effect=fake_agentic_loop):
        await agent.run(make_ctx())

    assert captured_deps
    assert captured_deps[0]["campaign_id"] == str(campaign_id)


# ── agentic_loop max_history_tokens ──────────────────────────────────────────

async def test_agentic_loop_truncates_old_rounds():
    from ze_core.orchestration.base_agent import _truncate_messages

    def tc(id_): return {"id": id_, "type": "function", "function": {"name": "web_search", "arguments": "{}"}}

    messages = [
        {"role": "user", "content": "find prospects"},
        {"role": "assistant", "content": None, "tool_calls": [tc("1"), tc("2")]},
        {"role": "tool", "tool_call_id": "1", "content": "x" * 4000},
        {"role": "tool", "tool_call_id": "2", "content": "x" * 4000},
        {"role": "assistant", "content": None, "tool_calls": [tc("3")]},
        {"role": "tool", "tool_call_id": "3", "content": "x" * 4000},
        {"role": "assistant", "content": "Done."},
    ]

    original_len = len(messages)
    _truncate_messages(messages, max_tokens=100)

    assert len(messages) < original_len
    for msg in messages:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected_ids = {tc["id"] for tc in msg["tool_calls"]}
            result_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
            assert expected_ids <= result_ids, "truncation left orphaned assistant turn"


async def test_agentic_loop_protects_last_4_messages():
    from ze_core.orchestration.base_agent import _truncate_messages

    def tc(id_): return {"id": id_, "type": "function", "function": {"name": "web_search", "arguments": "{}"}}

    tail = [
        {"role": "assistant", "content": None, "tool_calls": [tc("recent-1")]},
        {"role": "tool", "tool_call_id": "recent-1", "content": "recent tool result"},
        {"role": "assistant", "content": "working"},
        {"role": "user", "content": "ok"},
    ]

    messages = [
        {"role": "assistant", "content": None, "tool_calls": [tc("old-1")]},
        {"role": "tool", "tool_call_id": "old-1", "content": "old content " * 100},
    ] + tail

    _truncate_messages(messages, max_tokens=10)

    for msg in tail:
        assert msg in messages, f"protected message was removed: {msg}"


# ── recover_stale_campaigns ───────────────────────────────────────────────────

async def test_recover_stale_campaigns():
    from ze_prospecting.jobs.campaigns import recover_stale_campaigns
    from unittest.mock import AsyncMock, MagicMock

    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 0")

    await recover_stale_campaigns(pool, timeout_minutes=10)

    pool.execute.assert_called_once()


async def test_recover_stale_campaigns_logs_when_rows_updated():
    from ze_prospecting.jobs.campaigns import recover_stale_campaigns

    pool = MagicMock()
    pool.execute = AsyncMock(return_value="UPDATE 3")

    await recover_stale_campaigns(pool, timeout_minutes=10)

    pool.execute.assert_called_once()
