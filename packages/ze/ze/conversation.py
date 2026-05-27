"""Graph turn helpers for Ze — builds state/config and interprets LangGraph outcomes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ze_core.interface.types import RawInput

if TYPE_CHECKING:
    from ze.container import Container


def make_graph_input(
    raw: RawInput,
    session_id: str,
    *,
    session_overrides: dict[str, str] | None = None,
) -> dict:
    """Build AgentState input for the main conversation graph from raw transport input."""
    modality = "voice" if raw.audio else "image" if raw.image else "text"
    return {
        "prompt": raw.text or "",
        "session_id": session_id,
        "session_overrides": session_overrides or {},
        "input_modality": modality,
        "audio_data": raw.audio,
        "audio_mime": raw.audio_mime,
        "image_data": raw.image,
        "image_mime": raw.image_mime,
        "image_caption": None,
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "pending_confirmation": False,
        "final_response": None,
        "error": None,
        "messages": [],
        "last_active_at": None,
        "workflow_id": None,
        "workflow_execution_id": None,
        "workflow_steps": None,
        "current_step_index": 0,
        "workflow_step_results": [],
        "dynamic_plan_steps": None,
        "dynamic_plan_high_risk": [],
    }


def make_graph_input_from_raw_text(prompt: str, session_id: str) -> dict:
    return make_graph_input(RawInput(text=prompt), session_id)


def extract_response(state: dict) -> str:
    """Return the best available response text from a completed graph state."""
    if state.get("final_response"):
        return state["final_response"]
    result = state.get("agent_result")
    if result and result.response:
        return result.response
    return ""


@dataclass
class TurnResult:
    """Outcome of one main-graph invocation (may pause at await_confirmation)."""

    final_state: dict
    config: dict
    interrupted: bool
    draft: str = ""
    confirm_agent: str = ""
    confirm_action: str = ""
    dynamic_plan_steps: list | None = None
    dynamic_plan_high_risk: list | None = None
    error: str | None = None
    response: str | None = None


def _confirmation_meta(final_state: dict) -> tuple[str, str, str]:
    result = final_state.get("agent_result")
    envelope = final_state.get("envelope")
    draft = result.response if result else ""
    agent = envelope.primary_agent if envelope else ""
    action = (
        envelope.subtasks[0].intent
        if envelope and envelope.subtasks
        else ""
    )
    return draft, agent, action


async def invoke_raw_turn(
    container: Container,
    session_id: str,
    raw: RawInput,
    *,
    config_extra: dict | None = None,
) -> TurnResult:
    """Run the conversation graph once from raw transport input and interpret the outcome."""
    graph_input = make_graph_input(raw, session_id)
    config = container.make_graph_config(session_id, **(config_extra or {}))

    final_state = await container.graph.ainvoke(graph_input, config)
    graph_state = await container.graph.aget_state(config)
    interrupted = bool(graph_state.next)
    draft, agent, action = _confirmation_meta(final_state)

    return TurnResult(
        final_state=final_state,
        config=config,
        interrupted=interrupted,
        draft=draft,
        confirm_agent=agent,
        confirm_action=action,
        dynamic_plan_steps=final_state.get("dynamic_plan_steps"),
        dynamic_plan_high_risk=final_state.get("dynamic_plan_high_risk"),
        error=final_state.get("error"),
        response=None if interrupted else extract_response(final_state),
    )


async def resume_turn(container: Container, config: dict) -> TurnResult:
    """Resume the graph after the user confirms (async confirmation path)."""
    session_id = config["configurable"]["thread_id"]
    final_state = await container.graph.ainvoke(None, config)
    return TurnResult(
        final_state=final_state,
        config=config,
        interrupted=False,
        error=final_state.get("error"),
        response=extract_response(final_state),
    )
