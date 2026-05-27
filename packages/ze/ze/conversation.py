"""Graph turn helpers for Ze — builds state/config and interprets LangGraph outcomes."""

from __future__ import annotations

from typing import Any

from ze_core.interface.types import ProcessedInput, RawInput


def make_graph_input(
    processed: ProcessedInput,
    session_id: str,
    *,
    session_overrides: dict[str, str] | None = None,
) -> dict:
    """Build AgentState input for the main conversation graph."""
    return {
        "prompt": processed.prompt,
        "session_id": session_id,
        "session_overrides": session_overrides or {},
        "input_modality": processed.input_modality,
        "image_data": processed.image_data,
        "image_mime": processed.image_mime,
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
    return make_graph_input(
        ProcessedInput(prompt=prompt, input_modality="text"),
        session_id,
    )


def extract_response(state: dict) -> str:
    """Return the best available response text from a completed graph state."""
    if state.get("final_response"):
        return state["final_response"]
    result = state.get("agent_result")
    if result and result.response:
        return result.response
    return ""


async def preprocess_raw(container: Any, raw: RawInput) -> ProcessedInput:
    if container.preprocessor is not None:
        return await container.preprocessor.process(raw, container.openrouter_client)
    modality = "voice" if raw.audio else "image" if raw.image else "text"
    return ProcessedInput(
        prompt=raw.text or "",
        input_modality=modality,
        image_data=raw.image,
        image_mime=raw.image_mime,
    )
