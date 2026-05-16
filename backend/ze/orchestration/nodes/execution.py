import asyncio

from ze.agents.base import BaseAgent
from ze.agents.registry import get_agent
from ze.agents.types import AgentContext, AgentResult
from ze.capability.gate import CapabilityGate
from ze.capability.types import GateDecision
from ze.errors import AgentTimeoutError
from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze.settings import Settings

log = get_logger(__name__)


async def capability_check(state: AgentState, config: dict) -> dict:
    """Evaluate capability gate for the primary agent and intent."""
    gate: CapabilityGate = config["configurable"]["capability_gate"]
    envelope = state["envelope"]
    primary = envelope.subtasks[0] if envelope and envelope.subtasks else None

    if primary is None:
        return {"gate_decision": GateDecision.BLOCKED}

    decision = gate.evaluate(
        agent=primary.agent,
        intent=primary.intent,
        session_overrides=state.get("session_overrides", {}),
    )
    return {"gate_decision": decision}


async def execute_tool(state: AgentState, config: dict) -> dict:
    """Run the primary agent and collect results. Handles compound tasks sequentially."""
    settings: Settings = config["configurable"]["settings"]
    envelope = state["envelope"]
    base_ctx = state["agent_context"]

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    if envelope.is_compound:
        return await _execute_compound(envelope.subtasks, base_ctx, settings)
    else:
        return await _execute_single(envelope.subtasks[0], base_ctx, settings)


async def draft_response(state: AgentState, config: dict) -> dict:
    """Run the agent in draft mode — no write tool calls, result goes to confirmation."""
    settings: Settings = config["configurable"]["settings"]
    envelope = state["envelope"]
    base_ctx = state["agent_context"]

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    subtask = envelope.subtasks[0]
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings)
    return {"agent_result": result, "pending_confirmation": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _execute_single(subtask, base_ctx: AgentContext, settings: Settings) -> dict:
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings)
    return {"agent_result": result, "subtask_results": []}


async def _execute_compound(subtasks, base_ctx: AgentContext, settings: Settings) -> dict:
    results: list[AgentResult] = []
    for subtask in subtasks:
        ctx = AgentContext(
            session_id=base_ctx.session_id,
            prompt=subtask.prompt,
            intent=subtask.intent,
            memory=base_ctx.memory,
        )
        result = await _run_with_timeout(subtask.agent, ctx, settings)
        results.append(result)
    return {"agent_result": None, "subtask_results": results}


async def _run_with_timeout(
    agent_name: str, ctx: AgentContext, settings: Settings
) -> AgentResult:
    agent: BaseAgent = get_agent(agent_name)
    timeout = float(settings.agent_configs.get(agent_name, {}).get("timeout", 30))
    try:
        return await asyncio.wait_for(agent.run(ctx), timeout=timeout)
    except asyncio.TimeoutError:
        raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")
