import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.memory.types import MemoryContext
from ze_core.orchestration.nodes.context import SESSION_HISTORY_LIMIT
from ze_core.orchestration.nodes.memory import synthesize, write_memory
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.routing.types import RoutingEnvelope, SubTask


def _ctx(prompt: str = "hello") -> AgentContext:
    return AgentContext(
        session_id="s1",
        prompt=prompt,
        intent="read",
        memory=MemoryContext(),
        messages=[],
    )


def _make_store() -> MagicMock:
    store = AsyncMock()
    store.write_episode = AsyncMock()
    store.propose_facts = AsyncMock()
    return store


def _make_embedder(vec=None) -> MagicMock:
    embedder = MagicMock()
    embedder.encode = MagicMock(return_value=vec or [0.1, 0.2])
    return embedder


def _config(store=None, embedder=None, thread_id="s1", client=None, settings=None) -> dict:
    return {
        "configurable": {
            "memory_store": store or _make_store(),
            "embedder": embedder or _make_embedder(),
            "thread_id": thread_id,
            "openrouter_client": client,
            "settings": settings,
        }
    }


class TestWriteMemory:
    async def test_skips_all_writes_on_eval_thread(self):
        store = _make_store()
        state = {
            "session_id": "eval-001",
            "agent_context": _ctx(),
            "agent_result": AgentResult(agent="a", response="r"),
            "subtask_results": [],
            "messages": [],
            "input_modality": "text",
        }
        result = await write_memory(state, _config(store=store, thread_id="eval-001"))
        store.write_episode.assert_not_awaited()
        store.propose_facts.assert_not_awaited()

    async def test_fires_write_episode_for_normal_thread(self):
        store = _make_store()
        state = {
            "session_id": "s1",
            "agent_context": _ctx("hello"),
            "agent_result": AgentResult(agent="a", response="resp"),
            "subtask_results": [],
            "messages": [],
            "input_modality": "text",
        }
        await write_memory(state, _config(store=store, thread_id="s1"))
        await asyncio.sleep(0)  # let fire-and-forget tasks run
        store.write_episode.assert_awaited_once()

    async def test_appends_to_messages_and_trims(self):
        existing = [{"role": "user", "content": f"m{i}"} for i in range(SESSION_HISTORY_LIMIT - 1)]
        state = {
            "session_id": "s1",
            "agent_context": _ctx("new prompt"),
            "agent_result": AgentResult(agent="a", response="response"),
            "subtask_results": [],
            "messages": existing,
            "input_modality": "text",
        }
        result = await write_memory(state, _config(thread_id="s1"))
        msgs = result["messages"]
        assert len(msgs) <= SESSION_HISTORY_LIMIT
        assert msgs[-1] == {"role": "assistant", "content": "response"}

    async def test_no_agent_context_returns_empty(self):
        result = await write_memory({"agent_context": None, "session_id": "s1"}, _config())
        assert result == {}

    async def test_image_turn_stores_caption(self):
        state = {
            "session_id": "s1",
            "agent_context": _ctx(),
            "agent_result": AgentResult(agent="a", response="r"),
            "subtask_results": [],
            "messages": [],
            "input_modality": "image",
            "image_caption": "a cat on a mat",
        }
        result = await write_memory(state, _config(thread_id="s1"))
        user_msgs = [m for m in result["messages"] if m["role"] == "user"]
        assert user_msgs[-1]["content"] == "[Image] a cat on a mat"

    async def test_compound_synthesizes_result(self):
        store = _make_store()
        envelope = RoutingEnvelope(
            primary_agent="a", confidence=0.9, score_gap=0.3,
            routing_method="embedding", is_compound=True,
            subtasks=[SubTask(agent="a", intent="read", prompt="p")],
            requires_synthesis=True,
        )
        state = {
            "session_id": "s1",
            "agent_context": _ctx(),
            "agent_result": None,
            "subtask_results": [AgentResult(agent="a", response="sub result")],
            "final_response": "synthesized",
            "envelope": envelope,
            "messages": [],
            "input_modality": "text",
        }
        result = await write_memory(state, _config(store=store, thread_id="s1"))
        assert any(m["content"] == "synthesized" for m in result["messages"])


class TestSynthesize:
    async def test_merges_subtask_responses(self):
        client = AsyncMock()
        client.complete = AsyncMock(return_value="merged answer")
        subtask_results = [
            AgentResult(agent="a", response="answer A"),
            AgentResult(agent="b", response="answer B"),
        ]
        state = {
            "session_id": "s1",
            "prompt": "complex question",
            "subtask_results": subtask_results,
        }
        result = await synthesize(state, _config(client=client))
        assert result["final_response"] == "merged answer"
        call_args = client.complete.call_args
        assert "answer A" in call_args[1]["messages"][0]["content"]

    async def test_empty_subtasks_returns_empty(self):
        state = {"session_id": "s1", "prompt": "q", "subtask_results": []}
        result = await synthesize(state, _config())
        assert result == {}
