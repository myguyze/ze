from unittest.mock import AsyncMock, MagicMock

import pytest

from ze_core.conversation import TurnResult, invoke_raw_turn, resume_turn
from ze_core.interface.types import RawInput


@pytest.fixture
def container():
    graph = MagicMock()
    graph.ainvoke = AsyncMock(
        return_value={
            "final_response": "Done.",
            "agent_result": None,
            "envelope": None,
            "dynamic_plan_steps": None,
            "dynamic_plan_high_risk": [],
            "error": None,
        },
    )
    graph.aget_state = AsyncMock(
        return_value=MagicMock(next=()),
    )

    c = MagicMock()
    c.graph = graph
    c._build_config = MagicMock(
        return_value={"configurable": {"thread_id": "42"}},
    )
    return c


async def test_invoke_raw_turn_completed(container):
    outcome = await invoke_raw_turn(container, "42", RawInput(text="hello"))
    assert isinstance(outcome, TurnResult)
    assert outcome.interrupted is False
    assert outcome.response == "Done."
    container.graph.ainvoke.assert_awaited_once()


async def test_invoke_raw_turn_interrupted(container):
    container.graph.aget_state.return_value = MagicMock(next=("await_confirmation",))

    class _Result:
        response = "draft text"

    class _Envelope:
        primary_agent = "calendar"
        subtasks = [MagicMock(intent="create")]

    container.graph.ainvoke.return_value = {
        "agent_result": _Result(),
        "envelope": _Envelope(),
        "dynamic_plan_steps": None,
        "error": None,
    }

    outcome = await invoke_raw_turn(container, "42", RawInput(text="book meeting"))
    assert outcome.interrupted is True
    assert outcome.draft == "draft text"
    assert outcome.confirm_agent == "calendar"
    assert outcome.confirm_action == "create"
    assert outcome.response is None


async def test_resume_turn(container):
    container.graph.ainvoke.return_value = {"final_response": "Created."}
    config = {"configurable": {"thread_id": "42"}}
    outcome = await resume_turn(container, config)
    assert outcome.response == "Created."
    container.graph.ainvoke.assert_awaited_with(None, config)
