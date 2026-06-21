from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_ingestion.sink import MemorySink


@pytest.fixture
def memory_store() -> AsyncMock:
    return AsyncMock()


async def test_push_calls_propose_facts(memory_store: AsyncMock) -> None:
    sink = MemorySink(memory_store)
    await sink.push(ingestion_id="abc", facts=["Python is popular.", "It runs on CPython."])
    memory_store.propose_facts.assert_called_once()
    proposed = memory_store.propose_facts.call_args.args[0]
    assert len(proposed) == 2
    assert proposed[0].predicate == "Python is popular."


async def test_push_empty_facts_skips_call(memory_store: AsyncMock) -> None:
    sink = MemorySink(memory_store)
    await sink.push(ingestion_id="abc", facts=[])
    memory_store.propose_facts.assert_not_called()


async def test_push_memory_store_exception_is_caught(memory_store: AsyncMock) -> None:
    memory_store.propose_facts.side_effect = RuntimeError("DB down")
    sink = MemorySink(memory_store)
    # Must not raise
    await sink.push(ingestion_id="abc", facts=["A fact."])
