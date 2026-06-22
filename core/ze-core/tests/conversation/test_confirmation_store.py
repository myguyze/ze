from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from ze_core.conversation.confirmations import PendingConfirmationStore


def _make_pool_mock(fetchrow=None, execute_result="DELETE 1"):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow)
    conn.execute = AsyncMock(return_value=execute_result)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AsyncContextManagerMock(conn))
    return pool, conn


class _AsyncContextManagerMock:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        pass


def _make_confirmation_row():
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "thread_id": "thread-1",
        "request_id": "req-1",
        "prompt": "Approve?",
        "actions": [{"label": "Approve", "value": "approve"}],
    }[key]
    return row


async def test_save_inserts_confirmation():
    pool, conn = _make_pool_mock()
    store = PendingConfirmationStore(pool=pool)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)

    await store.save("thread-1", "req-1", "Approve?", [{"label": "Approve"}], expires)

    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert "INSERT INTO pending_confirmations" in sql


async def test_get_any_pending_returns_dict():
    row = _make_confirmation_row()
    pool, conn = _make_pool_mock(fetchrow=row)
    store = PendingConfirmationStore(pool=pool)

    result = await store.get_any_pending()

    assert result is not None
    assert result["thread_id"] == "thread-1"
    assert result["prompt"] == "Approve?"


async def test_get_any_pending_returns_none_when_empty():
    pool, conn = _make_pool_mock(fetchrow=None)
    store = PendingConfirmationStore(pool=pool)

    result = await store.get_any_pending()

    assert result is None


async def test_clear_returns_true_when_deleted():
    pool, conn = _make_pool_mock(execute_result="DELETE 1")
    store = PendingConfirmationStore(pool=pool)

    deleted = await store.clear("thread-1")

    assert deleted is True
    conn.execute.assert_called_once()


async def test_clear_returns_false_when_missing():
    pool, conn = _make_pool_mock(execute_result="DELETE 0")
    store = PendingConfirmationStore(pool=pool)

    deleted = await store.clear("thread-1")

    assert deleted is False
