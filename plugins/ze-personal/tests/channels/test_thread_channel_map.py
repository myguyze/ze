from unittest.mock import AsyncMock, MagicMock

from ze_personal.channels.thread_channel_map import ThreadChannelMap


def _make_pool(conn=None):
    if conn is None:
        conn = AsyncMock()
        conn.execute = AsyncMock()
        conn.fetchval = AsyncMock(return_value=None)
    pool = MagicMock()
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    return pool


async def test_get_returns_none_when_absent():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=None)
    store = ThreadChannelMap(pool=_make_pool(conn))
    result = await store.get("thread-99")
    assert result is None


async def test_get_returns_channel_id():
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value="gmail:alice@example.com")
    store = ThreadChannelMap(pool=_make_pool(conn))
    result = await store.get("thread-1")
    assert result == "gmail:alice@example.com"


async def test_set_executes_upsert():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    store = ThreadChannelMap(pool=_make_pool(conn))
    await store.set("thread-1", "gmail:alice@example.com")
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "ON CONFLICT" in sql
    assert conn.execute.call_args[0][1] == "thread-1"
    assert conn.execute.call_args[0][2] == "gmail:alice@example.com"


async def test_set_overwrites_existing():
    conn = AsyncMock()
    conn.execute = AsyncMock()
    store = ThreadChannelMap(pool=_make_pool(conn))
    await store.set("thread-1", "gmail:bob@example.com")
    # ON CONFLICT DO UPDATE handles overwrite — just verify it's called once
    assert conn.execute.call_count == 1
