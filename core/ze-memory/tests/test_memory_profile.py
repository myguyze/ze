from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


from ze_memory import admin as memory_admin


def make_pool(fetchrow_return=None):
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.execute = AsyncMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool


async def test_get_profile_returns_data():
    now = datetime(2026, 5, 20, 2, 0, 0, tzinfo=timezone.utc)
    row = {
        "preferences": "Likes brevity.",
        "habits": "Works mornings.",
        "topics": "AI.",
        "relationships": "Has a cat.",
        "goals": "Ship Ze.",
        "updated_at": now,
        "version": 3,
    }
    pool = make_pool(fetchrow_return=row)
    result = await memory_admin.get_profile(pool)
    assert result is not None
    assert result["preferences"] == "Likes brevity."
    assert result["version"] == 3


async def test_get_profile_none_when_all_empty():
    row = {
        "preferences": "",
        "habits": "",
        "topics": "",
        "relationships": "",
        "goals": "",
        "updated_at": datetime(2026, 5, 20, tzinfo=timezone.utc),
        "version": 0,
    }
    pool = make_pool(fetchrow_return=row)
    assert await memory_admin.get_profile(pool) is None


async def test_get_profile_none_when_no_row():
    pool = make_pool(fetchrow_return=None)
    assert await memory_admin.get_profile(pool) is None
