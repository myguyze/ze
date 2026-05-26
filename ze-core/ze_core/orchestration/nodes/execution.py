from __future__ import annotations

import asyncio
import base64
from typing import Any

from ze_core.capability.types import GateDecision
from ze_core.errors import AgentTimeoutError
from ze_core.logging import get_logger
from ze_core.orchestration.registry import get_agent
from ze_core.orchestration.state import AgentState
from ze_core.orchestration.types import AgentContext, AgentResult

log = get_logger(__name__)


async def capability_check(state: AgentState, config: dict) -> dict:
    from ze_core.capability.gate import CapabilityGate

    gate: CapabilityGate = config["configurable"]["capability_gate"]
    envelope = state.get("envelope")
    primary = envelope.subtasks[0] if envelope and envelope.subtasks else None

    if primary is None:
        return {"gate_decision": GateDecision.BLOCKED}

    decision = gate.evaluate(
        agent=primary.agent,
        intent=primary.intent,
        session_overrides=state.get("session_overrides") or {},
    )
    return {"gate_decision": decision}


async def execute_tool(state: AgentState, config: dict) -> dict:
    envelope = state.get("envelope")
    base_ctx = state.get("agent_context")

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    gate_decision: GateDecision = state.get("gate_decision") or GateDecision.EXECUTE
    reporter = config["configurable"].get("reporter")
    token_queue: asyncio.Queue | None = config["configurable"].get("token_queue")

    if envelope.is_compound:
        return await _execute_compound(
            envelope.subtasks, base_ctx, gate_decision, state,
            is_sequential=envelope.is_sequential,
            reporter=reporter,
        )
    return await _execute_single(
        envelope.subtasks[0], base_ctx, gate_decision, state,
        token_queue=token_queue,
        reporter=reporter,
    )


async def draft_response(state: AgentState, config: dict) -> dict:
    envelope = state.get("envelope")
    base_ctx = state.get("agent_context")

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    subtask = envelope.subtasks[0]
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=GateDecision.DRAFT,
        memory=base_ctx.memory,
        model=subtask.model or None,
        messages=_build_messages(state, subtask.agent, base_ctx),
    )
    result = await _run_with_timeout(subtask.agent, ctx)
    return {"agent_result": result, "pending_confirmation": True}


async def await_confirmation(state: AgentState, config: dict) -> dict:
    log.info(
        "orchestration_confirmation_received",
        session_id=state["session_id"],
        agent=state["envelope"].primary_agent if state.get("envelope") else None,
    )
    return {"pending_confirmation": False, "gate_decision": GateDecision.EXECUTE}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_messages(state: dict, agent_name: str, base_ctx: AgentContext) -> list[dict]:
    if state.get("image_data"):
        return [_build_image_message(state)]
    return base_ctx.messages


def _build_image_message(state: dict) -> dict:
    prompt = state.get("prompt") or state.get("image_caption") or ""
    mime = state.get("image_mime", "image/jpeg")
    content: list = [
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{base64.b64encode(state['image_data']).decode()}",
                "detail": "auto",
            },
        }
    ]
    if prompt:
        content.append({"type": "text", "text": prompt})
    return {"role": "user", "content": content}


async def _execute_single(
    subtask: Any,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    state: dict,
    token_queue: asyncio.Queue | None = None,
    reporter: Any = None,
) -> dict:
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=gate_decision,
        memory=base_ctx.memory,
        model=subtask.model or None,
        messages=_build_messages(state, subtask.agent, base_ctx),
        reporter=reporter,
    )
    result = await _run_with_timeout(subtask.agent, ctx, token_queue=token_queue)
    return {"agent_result": result, "subtask_results": []}


async def _execute_compound(
    subtasks: list,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    state: dict,
    is_sequential: bool = False,
    reporter: Any = None,
) -> dict:
    def _make_ctx(subtask: Any) -> AgentContext:
        return AgentContext(
            session_id=base_ctx.session_id,
            prompt=subtask.prompt,
            intent=subtask.intent,
            gate_decision=gate_decision,
            memory=base_ctx.memory,
            model=subtask.model or None,
            messages=_build_messages(state, subtask.agent, base_ctx),
            reporter=reporter,
        )

    if is_sequential:
        results: list[AgentResult] = []
        for subtask in subtasks:
            result = await _run_with_timeout(subtask.agent, _make_ctx(subtask))
            results.append(result)
    else:
        results = list(
            await asyncio.gather(
                *[_run_with_timeout(st.agent, _make_ctx(st)) for st in subtasks]
            )
        )

    return {"agent_result": None, "subtask_results": results}


async def _run_with_timeout(
    agent_name: str,
    ctx: AgentContext,
    token_queue: asyncio.Queue | None = None,
) -> AgentResult:
    instance = get_agent(agent_name)
    timeout = float(getattr(type(instance), "timeout", 30))

    if token_queue is not None:
        async def _stream_and_collect() -> AgentResult:
            tokens: list[str] = []
            try:
                async for token in instance.stream(ctx):
                    tokens.append(token)
                    await token_queue.put(token)
            finally:
                await token_queue.put(None)
            return AgentResult(agent=agent_name, response="".join(tokens))

        try:
            return await asyncio.wait_for(_stream_and_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")

    try:
        return await asyncio.wait_for(instance.run(ctx), timeout=timeout)
    except asyncio.TimeoutError:
        raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")
