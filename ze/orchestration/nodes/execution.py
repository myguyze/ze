import asyncio

from langchain_core.runnables import RunnableConfig

from ze.agents.base import BaseAgent
from ze.agents.registry import get_agent
from ze.agents.types import AgentContext, AgentResult
from ze.capability.gate import CapabilityGate
from ze.capability.types import GateDecision
from ze.errors import AgentTimeoutError
from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze.settings import Settings
from ze.telemetry.context import set_agent_context

log = get_logger(__name__)


async def capability_check(state: AgentState, config: RunnableConfig) -> dict:
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


async def execute_tool(state: AgentState, config: RunnableConfig) -> dict:
    """Run the primary agent and collect results. Handles compound tasks sequentially."""
    settings: Settings = config["configurable"]["settings"]
    token_queue: asyncio.Queue | None = config["configurable"].get("token_queue")
    envelope = state["envelope"]
    base_ctx = state["agent_context"]

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    gate_decision: GateDecision = state.get("gate_decision") or GateDecision.EXECUTE

    if envelope.is_compound:
        return await _execute_compound(envelope.subtasks, base_ctx, gate_decision, settings)
    else:
        return await _execute_single(envelope.subtasks[0], base_ctx, gate_decision, settings, token_queue)


async def draft_response(state: AgentState, config: RunnableConfig) -> dict:
    """Run the agent in draft mode — write tools are suppressed inside call_tool()."""
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
        gate_decision=GateDecision.DRAFT,
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings)
    return {"agent_result": result, "pending_confirmation": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _execute_single(
    subtask,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    settings: Settings,
    token_queue: asyncio.Queue | None = None,
) -> dict:
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=gate_decision,
        memory=base_ctx.memory,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings, token_queue)
    return {"agent_result": result, "subtask_results": []}


async def _execute_compound(
    subtasks,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    settings: Settings,
) -> dict:
    results: list[AgentResult] = []
    for subtask in subtasks:
        ctx = AgentContext(
            session_id=base_ctx.session_id,
            prompt=subtask.prompt,
            intent=subtask.intent,
            gate_decision=gate_decision,
            memory=base_ctx.memory,
        )
        result = await _run_with_timeout(subtask.agent, ctx, settings)
        results.append(result)
    return {"agent_result": None, "subtask_results": results}


async def _run_with_timeout(
    agent_name: str,
    ctx: AgentContext,
    settings: Settings,
    token_queue: asyncio.Queue | None = None,
) -> AgentResult:
    set_agent_context(agent_name)
    agent: BaseAgent = get_agent(agent_name)
    timeout = float(settings.agent_configs.get(agent_name, {}).get("timeout", 30))

    if token_queue is not None:
        async def _stream_and_collect() -> AgentResult:
            tokens: list[str] = []
            try:
                async for token in agent.stream(ctx):
                    tokens.append(token)
                    await token_queue.put(token)
            finally:
                await token_queue.put(None)  # sentinel — always signal completion
            return AgentResult(agent=agent_name, response="".join(tokens))

        try:
            return await asyncio.wait_for(_stream_and_collect(), timeout=timeout)
        except asyncio.TimeoutError:
            raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")

    try:
        return await asyncio.wait_for(agent.run(ctx), timeout=timeout)
    except asyncio.TimeoutError:
        raise AgentTimeoutError(f"{agent_name} timed out after {timeout}s")
