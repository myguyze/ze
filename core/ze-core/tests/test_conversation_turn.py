from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.conversation import TurnResult, invoke_raw_turn, make_graph_input, resume_turn
from ze_agents.interface.types import RawInput


def test_graph_input_preserves_conversation_history():
    """messages/last_active_at must NOT be in the input dict: LangGraph input keys
    overwrite checkpointed channels, which would wipe history every turn and break
    follow-up questions."""
    graph_input = make_graph_input(RawInput(text="are these recent?"), "s1")
    assert "messages" not in graph_input
    assert "last_active_at" not in graph_input


async def _astream_events(events):
    for e in events:
        yield e


@pytest.fixture
def container():
    graph = MagicMock()
    graph.name = "LangGraph"
    graph.astream_events = lambda *a, **kw: _astream_events([
        {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {
                "output": {
                    "final_response": "Done.",
                    "agent_result": None,
                    "envelope": None,
                    "dynamic_plan_steps": None,
                    "dynamic_plan_high_risk": [],
                    "error": None,
                }
            },
        }
    ])
    graph.aget_state = AsyncMock(return_value=MagicMock(next=()))

    c = MagicMock()
    c.graph = graph
    c.interface = None
    c._build_config = MagicMock(return_value={"configurable": {"thread_id": "42"}})
    return c


async def test_invoke_raw_turn_completed(container):
    outcome = await invoke_raw_turn(container, "42", RawInput(text="hello"))
    assert isinstance(outcome, TurnResult)
    assert outcome.interrupted is False
    assert outcome.response == "Done."


async def test_invoke_raw_turn_interrupted(container):
    class _Result:
        response = "draft text"

    class _Envelope:
        primary_agent = "calendar"
        subtasks = [MagicMock(intent="create")]

    state_values = {
        "agent_result": _Result(),
        "envelope": _Envelope(),
        "dynamic_plan_steps": None,
        "dynamic_plan_high_risk": [],
        "error": None,
    }
    graph_state = MagicMock(next=("await_confirmation",))
    graph_state.values = state_values
    container.graph.aget_state.return_value = graph_state
    container.graph.astream_events = lambda *a, **kw: _astream_events([])

    outcome = await invoke_raw_turn(container, "42", RawInput(text="book meeting"))
    assert outcome.interrupted is True
    assert outcome.draft == "draft text"
    assert outcome.confirm_agent == "calendar"
    assert outcome.confirm_action == "create"
    assert outcome.response is None


async def test_resume_turn(container):
    container.graph.ainvoke = AsyncMock(return_value={"final_response": "Created."})
    config = {"configurable": {"thread_id": "42"}}
    outcome = await resume_turn(container, config)
    assert outcome.response == "Created."
    container.graph.ainvoke.assert_awaited_with(None, config)
