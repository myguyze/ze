"""Built-in delegate_to_agent harness tool.

Not registered via @tool — handled specially in agentic_loop alongside
_OPENROUTER_TOOL_SCHEMAS, which keeps it out of the tool registry and avoids
conflicts with clear_tool_registry() in tests.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from ze_core.errors import ZeCoreError
from ze_core.logging import get_logger
from ze_core.orchestration.types import AgentContext, ToolCall

if TYPE_CHECKING:
    pass

log = get_logger(__name__)

DELEGATE_TOOL_NAME = "delegate_to_agent"
_DELEGATE_MAX_DEPTH = 2

DELEGATE_TOOL_SCHEMA: dict = {
    "name": DELEGATE_TOOL_NAME,
    "description": (
        "Delegate a subtask to a specialised agent and return its complete response. "
        "Use when the current task is better handled by a different agent — for example, "
        "delegating calendar lookups to the calendar agent while the research agent "
        "focuses on web search."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "agent_name": {
                "type": "string",
                "description": "Name of the agent to delegate to.",
            },
            "task": {
                "type": "string",
                "description": "The subtask to hand off.",
            },
            "context": {
                "type": "string",
                "description": "Optional extra context to prepend to the task.",
            },
        },
        "required": ["agent_name", "task"],
    },
}


async def run_delegate(
    arguments: dict[str, Any],
    ctx: AgentContext,
    iteration: int,
) -> ToolCall:
    """Execute a delegate_to_agent tool call from inside agentic_loop."""
    from ze_core.orchestration.registry import get_agent

    agent_name: str = arguments.get("agent_name", "")
    task: str = arguments.get("task", "")
    context: str | None = arguments.get("context")

    depth: int = ctx.extensions.get("_delegate_depth", 0)  # type: ignore[assignment]

    start = time.monotonic()

    if depth >= _DELEGATE_MAX_DEPTH:
        msg = f"delegation depth limit exceeded (max {_DELEGATE_MAX_DEPTH})"
        log.warning("delegate_depth_exceeded", agent=agent_name, depth=depth)
        return ToolCall(
            tool_name=DELEGATE_TOOL_NAME,
            args=arguments,
            result=None,
            duration_ms=0,
            success=False,
            error=msg,
        )

    try:
        instance = get_agent(agent_name)
    except Exception as exc:
        return ToolCall(
            tool_name=DELEGATE_TOOL_NAME,
            args=arguments,
            result=None,
            duration_ms=0,
            success=False,
            error=str(exc),
        )

    prompt = task if context is None else f"{context}\n\n{task}"
    sub_ctx = AgentContext(
        session_id=ctx.session_id,
        prompt=prompt,
        intent=agent_name,
        gate_decision=ctx.gate_decision,
        memory=ctx.memory,
        contacts=ctx.contacts,
        persona=ctx.persona,
        model=None,
        messages=[{"role": "user", "content": task}],
        reporter=ctx.reporter,
        identity_builder=ctx.identity_builder,
        abort_token=ctx.abort_token,
        extensions={"_delegate_depth": depth + 1},
    )

    log.info("delegate_start", from_agent=ctx.intent, to_agent=agent_name, depth=depth)
    try:
        result = await instance.run(sub_ctx)
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning("delegate_error", to_agent=agent_name, error=str(exc))
        return ToolCall(
            tool_name=DELEGATE_TOOL_NAME,
            args=arguments,
            result=None,
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
        )

    duration_ms = int((time.monotonic() - start) * 1000)
    log.info("delegate_done", to_agent=agent_name, duration_ms=duration_ms)
    return ToolCall(
        tool_name=DELEGATE_TOOL_NAME,
        args=arguments,
        result=result.response,
        duration_ms=duration_ms,
        success=True,
    )
