from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ze.agents.prospecting.agent import ProspectingAgent
from ze.agents.types import AgentContext, AgentResult, ToolCall
from ze.contacts.types import PersonContext
from ze.logging import configure_logging
from ze.memory.types import MemoryContext


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


def make_campaign_row(campaign_id=None):
    row = MagicMock()
    row.__getitem__ = lambda self, key: campaign_id or uuid4() if key == "id" else 0
    return row


def make_conn(campaign_id=None):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=make_campaign_row(campaign_id))
    conn.execute = AsyncMock()
    return conn


def make_pool(conn=None):
    if conn is None:
        conn = make_conn()
    pool = MagicMock()
    pool.execute = AsyncMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


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
    pool=None,
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
    if pool is None:
        pool = make_pool()
    return ProspectingAgent(
        openrouter_client=client,
        settings=make_settings(),
        browser_client=browser_client,
        person_store=person_store,
        pool=pool,
    )


@pytest.fixture(autouse=True)
def setup_logging():
    configure_logging()


# ── Registration ──────────────────────────────────────────────────────────────

def test_prospecting_agent_is_registered():
    from ze.agents.registry import _registry
    assert "prospecting" in _registry


# ── run() ─────────────────────────────────────────────────────────────────────

async def test_prospecting_agent_run_creates_campaign():
    campaign_id = uuid4()
    conn = make_conn(campaign_id)
    pool = make_pool(conn)

    agent = make_agent(pool=pool)
    ctx = make_ctx()

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("Found prospects.", []))):
        result = await agent.run(ctx)

    assert isinstance(result, AgentResult)
    assert result.agent == "prospecting"
    # Campaign INSERT called
    conn.fetchrow.assert_called_once()
    insert_sql = conn.fetchrow.call_args[0][0]
    assert "INSERT INTO prospect_campaigns" in insert_sql


async def test_prospecting_agent_run_sets_status_complete():
    campaign_id = uuid4()
    conn = make_conn(campaign_id)
    pool = make_pool(conn)

    agent = make_agent(pool=pool)

    with patch.object(agent, "agentic_loop", AsyncMock(return_value=("Summary here.", []))):
        await agent.run(make_ctx())

    # UPDATE to complete called
    execute_calls = [str(c) for c in conn.execute.call_args_list]
    assert any("complete" in c for c in execute_calls)


async def test_prospecting_agent_failure_sets_status_failed():
    campaign_id = uuid4()
    conn = make_conn(campaign_id)
    pool = make_pool(conn)

    agent = make_agent(pool=pool)

    with patch.object(agent, "agentic_loop", AsyncMock(side_effect=RuntimeError("LLM error"))):
        with pytest.raises(RuntimeError, match="LLM error"):
            await agent.run(make_ctx())

    execute_calls = [str(c) for c in conn.execute.call_args_list]
    assert any("failed" in c for c in execute_calls)


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
    assert "web_search" in captured_tool_names


async def test_prospecting_agent_passes_campaign_id_in_deps():
    campaign_id = uuid4()
    conn = make_conn(campaign_id)
    pool = make_pool(conn)

    captured_deps: list[dict] = []

    async def fake_agentic_loop(ctx, *, client, messages, system, deps, **kwargs):
        captured_deps.append(deps)
        return "done", []

    agent = make_agent(pool=pool)

    with patch.object(agent, "agentic_loop", side_effect=fake_agentic_loop):
        await agent.run(make_ctx())

    assert captured_deps
    assert captured_deps[0]["campaign_id"] == str(campaign_id)


# ── agentic_loop max_history_tokens ──────────────────────────────────────────

async def test_agentic_loop_truncates_old_tool_messages():
    from ze.agents.base import _truncate_messages

    messages = [
        {"role": "user", "content": "find prospects"},
        {"role": "assistant", "content": None, "tool_calls": []},
        {"role": "tool", "tool_call_id": "1", "content": "x" * 4000},
        {"role": "tool", "tool_call_id": "2", "content": "x" * 4000},
        {"role": "tool", "tool_call_id": "3", "content": "x" * 4000},
        {"role": "tool", "tool_call_id": "4", "content": "x" * 4000},
        {"role": "tool", "tool_call_id": "5", "content": "x" * 4000},
    ]

    original_len = len(messages)
    _truncate_messages(messages, max_tokens=100)

    assert len(messages) < original_len


async def test_agentic_loop_protects_last_4_messages():
    from ze.agents.base import _truncate_messages

    tail = [
        {"role": "tool", "tool_call_id": "recent-1", "content": "recent tool result"},
        {"role": "assistant", "content": "working"},
        {"role": "tool", "tool_call_id": "recent-2", "content": "another recent"},
        {"role": "user", "content": "ok"},
    ]

    messages = [
        {"role": "tool", "tool_call_id": "old-1", "content": "old content " * 100},
        {"role": "tool", "tool_call_id": "old-2", "content": "old content " * 100},
    ] + tail

    _truncate_messages(messages, max_tokens=10)

    remaining_ids = {m.get("tool_call_id") for m in messages if m.get("role") == "tool"}
    for m in tail:
        if m.get("tool_call_id"):
            assert m["tool_call_id"] in remaining_ids


# ── recover_stale_campaigns ───────────────────────────────────────────────────

async def test_recover_stale_campaigns():
    from ze.proactive.prospecting import recover_stale_campaigns

    pool = MagicMock()
    pool.execute = AsyncMock()

    await recover_stale_campaigns(pool, timeout_minutes=60)

    pool.execute.assert_called_once()
    sql = pool.execute.call_args[0][0]
    assert "UPDATE prospect_campaigns" in sql
    assert "failed" in sql
    assert "running" in sql
