from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ze_agents.types import AgentResult, ToolCall
from ze_automation.workflow.types import WorkflowStep
from ze_personal.graph.workflow import _resolve_step_output, verify_step


def test_resolve_step_output_prefers_final_response():
    state = {
        "final_response": "synthesized",
        "agent_result": AgentResult(agent="news", response="ignored"),
    }
    assert _resolve_step_output(state) == "synthesized"


def test_resolve_step_output_uses_agent_result():
    state = {
        "agent_result": AgentResult(agent="news", response="headlines"),
        "subtask_results": [AgentResult(agent="news", response="fallback")],
    }
    assert _resolve_step_output(state) == "headlines"


def test_resolve_step_output_joins_subtask_results():
    state = {
        "subtask_results": [
            AgentResult(agent="news", response="first"),
            AgentResult(agent="research", response="second"),
        ],
    }
    assert _resolve_step_output(state) == "first\n\nsecond"


@pytest.mark.asyncio
async def test_verify_step_accepts_subtask_results_without_agent_result():
    store = MagicMock()
    store.record_step = AsyncMock()
    config = {
        "configurable": {
            "workflow_store": store,
            "openrouter_client": MagicMock(),
        }
    }
    state = {
        "workflow_steps": [WorkflowStep(task="search news", intent="read")],
        "current_step_index": 0,
        "workflow_execution_id": uuid4(),
        "workflow_step_results": [],
        "agent_result": None,
        "subtask_results": [AgentResult(agent="news", response="article summary")],
    }

    result = await verify_step(state, config)

    assert result["current_step_index"] == 1
    assert len(result["workflow_step_results"]) == 1
    assert result["workflow_step_results"][0].success is True
    assert result["workflow_step_results"][0].output == "article summary"


@pytest.mark.asyncio
async def test_verify_step_fails_when_all_outputs_empty():
    store = MagicMock()
    store.record_step = AsyncMock()
    config = {
        "configurable": {
            "workflow_store": store,
            "openrouter_client": MagicMock(),
        }
    }
    state = {
        "workflow_steps": [WorkflowStep(task="search news", intent="read")],
        "current_step_index": 0,
        "workflow_execution_id": uuid4(),
        "workflow_step_results": [],
        "agent_result": AgentResult(agent="news", response=""),
        "subtask_results": [],
    }

    result = await verify_step(state, config)

    assert result["workflow_step_results"][-1].success is False
    assert result["workflow_step_results"][-1].error == "Step produced empty output"
