import asyncio
import base64

from langchain_core.runnables import RunnableConfig

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import get_agent, get_agent_class
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.capability.types import GateDecision
from ze_core.errors import AgentTimeoutError
from ze.logging import get_logger
from ze.orchestration.state import AgentState
from ze.settings import Settings
from ze_core.telemetry.context import set_agent_context

log = get_logger(__name__)


async def execute_tool(state: AgentState, config: RunnableConfig) -> dict:
    """Run the primary agent and collect results. Compound tasks run in parallel unless sequential."""
    settings: Settings = config["configurable"]["settings"]
    token_queue: asyncio.Queue | None = config["configurable"].get("token_queue")
    envelope = state["envelope"]
    base_ctx = state["agent_context"]

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    gate_decision: GateDecision = state.get("gate_decision") or GateDecision.EXECUTE

    reporter = config["configurable"].get("reporter")

    if envelope.is_compound:
        return await _execute_compound(
            envelope.subtasks, base_ctx, gate_decision, settings, state,
            is_sequential=envelope.is_sequential,
            reporter=reporter,
        )
    else:
        return await _execute_single(envelope.subtasks[0], base_ctx, gate_decision, settings, token_queue, state, reporter=reporter)


async def draft_response(state: AgentState, config: RunnableConfig) -> dict:
    """Run the agent in draft mode — write tools are suppressed inside call_tool()."""
    settings: Settings = config["configurable"]["settings"]
    envelope = state["envelope"]
    base_ctx = state["agent_context"]

    if not envelope or not base_ctx:
        return {"error": "Missing routing envelope or agent context"}

    subtask = envelope.subtasks[0]
    if state.get("image_data"):
        messages = [_build_user_message(state, get_agent_class(subtask.agent))]
    else:
        messages = base_ctx.messages
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=GateDecision.DRAFT,
        memory=base_ctx.memory,
        model=subtask.model if subtask.model else None,
        messages=messages,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings)
    return {"agent_result": result, "pending_confirmation": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(state: dict, agent_cls: type) -> dict:
    """Build the user message dict, including image content block for vision-capable agents."""
    prompt = state.get("prompt") or state.get("image_caption") or ""
    vision_capable = getattr(agent_cls, "vision_capable", True)

    if state.get("image_data") and vision_capable:
        mime = state.get("image_mime", "image/jpeg")
        content: list = [
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime};base64,{base64.b64encode(state['image_data']).decode()}",
                    "detail": "auto",
                },
            },
        ]
        if prompt:
            content.append({"type": "text", "text": prompt})
        return {"role": "user", "content": content}

    return {"role": "user", "content": prompt}


async def _execute_single(
    subtask,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    settings: Settings,
    token_queue: asyncio.Queue | None = None,
    state: dict | None = None,
    reporter=None,
) -> dict:
    if state is not None and state.get("image_data"):
        messages = [_build_user_message(state, get_agent_class(subtask.agent))]
    else:
        messages = base_ctx.messages
    ctx = AgentContext(
        session_id=base_ctx.session_id,
        prompt=subtask.prompt,
        intent=subtask.intent,
        gate_decision=gate_decision,
        memory=base_ctx.memory,
        model=subtask.model if subtask.model else None,
        messages=messages,
        reporter=reporter,
    )
    result = await _run_with_timeout(subtask.agent, ctx, settings, token_queue)
    return {"agent_result": result, "subtask_results": []}


async def _execute_compound(
    subtasks,
    base_ctx: AgentContext,
    gate_decision: GateDecision,
    settings: Settings,
    state: dict | None = None,
    is_sequential: bool = False,
    reporter=None,
) -> dict:
    def _make_ctx(subtask) -> AgentContext:
        if state is not None and state.get("image_data"):
            messages = [_build_user_message(state, get_agent_class(subtask.agent))]
        else:
            messages = base_ctx.messages
        return AgentContext(
            session_id=base_ctx.session_id,
            prompt=subtask.prompt,
            intent=subtask.intent,
            gate_decision=gate_decision,
            memory=base_ctx.memory,
            model=subtask.model if subtask.model else None,
            messages=messages,
            reporter=reporter,
        )

    if is_sequential:
        results: list[AgentResult] = []
        for subtask in subtasks:
            result = await _run_with_timeout(subtask.agent, _make_ctx(subtask), settings)
            results.append(result)
    else:
        results = list(
            await asyncio.gather(
                *[_run_with_timeout(subtask.agent, _make_ctx(subtask), settings) for subtask in subtasks]
            )
        )

    return {"agent_result": None, "subtask_results": results}


async def _run_with_timeout(
    agent_name: str,
    ctx: AgentContext,
    settings: Settings,
    token_queue: asyncio.Queue | None = None,
) -> AgentResult:
    set_agent_context(agent_name)
    agent: BaseAgent = get_agent(agent_name)
    timeout = float(getattr(get_agent_class(agent_name), "timeout", 30))

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
