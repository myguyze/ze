from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime
from functools import cached_property
from typing import Any, AsyncIterator

from ze_agents.client import LLMClient
from ze_agents.defaults import MODEL_AGENT_DEFAULT, MODEL_AGENT_TIMEOUT
from ze_agents.errors import AgentAbortedError, AgentError, HookAbort, ToolBlockedError
from ze_agents.hooks import (
    LoopEndEvent,
    LoopStartEvent,
    ToolEndEvent,
    ToolStartEvent,
    get_hooks,
)
from ze_agents.logging import get_logger
from ze_agents.types import AgentContext, AgentResult, GateDecision, ToolCall

# Schemas for OpenRouter server-side tools (executed by OpenRouter, not the client).
_OPENROUTER_TOOL_SCHEMAS: dict[str, dict] = {
    "openrouter:web_search": {"type": "openrouter:web_search"},
}

log = get_logger(__name__)


def _is_openrouter_server_tool(name: str) -> bool:
    """Return True for OpenRouter-native tools that are not in the local @tool registry."""
    if name in _OPENROUTER_TOOL_SCHEMAS:
        return True
    return name == "openrouter" or name.startswith(("openrouter:", "openrouter_"))


def _canonical_openrouter_tool_name(name: str) -> str:
    """Normalize variant OpenRouter tool names returned by the API."""
    if name in _OPENROUTER_TOOL_SCHEMAS:
        return name
    if name.startswith("openrouter_"):
        return name.replace("_", ":", 1)
    if name == "openrouter":
        return "openrouter:web_search"
    return name


class BaseAgent(ABC):
    name: str
    description: str
    model: str = MODEL_AGENT_DEFAULT
    model_simple: str | None = None
    vision_capable: bool = False
    timeout: int = MODEL_AGENT_TIMEOUT
    enabled: bool = True
    capabilities: dict[str, Any] = {}
    intent_map: dict[str, str] = {}
    tools: list[str] = []
    system_prompt: str = ""

    @abstractmethod
    async def run(self, ctx: AgentContext) -> AgentResult:
        """Execute the agent and return a complete result."""

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        """Stream response tokens. Default raises NotImplementedError."""
        raise NotImplementedError
        yield  # make type checkers happy

    async def startup(self) -> None:
        """Called once after DI wiring. Override for warmup."""

    async def shutdown(self) -> None:
        """Called during app shutdown. Override for cleanup."""

    @cached_property
    def _log(self):
        return get_logger(type(self).__module__)

    async def emit(self, ctx: AgentContext, key: str, **kwargs: str) -> None:
        """Emit a progress message. No-op when no reporter is attached (e.g. tests)."""
        if ctx.reporter is not None:
            await ctx.reporter.emit(key, **kwargs)

    def _model(self, ctx: AgentContext | None = None) -> str:
        if ctx is not None and ctx.model is not None:
            return ctx.model
        return self.model

    def _timeout(self) -> int:
        return int(self.timeout)

    def _format_memory(self, ctx: AgentContext) -> str:
        memory = ctx.memory
        if memory is None:
            return "(none)"
        facts = getattr(memory, "facts", []) or []
        lines = [f"- {getattr(f, 'predicate', getattr(f, 'key', '?'))}: {f.value}" for f in facts]
        return "\n".join(lines) if lines else "(none)"

    def _format_contacts(self, ctx: AgentContext) -> str:
        if ctx.contacts is None:
            return ""
        lines = []
        for p in ctx.contacts.people:
            line = f"- {p.name}: {p.relationship_to_user}"
            if p.notes:
                line += f" ({p.notes})"
            lines.append(line)
        return "\n".join(lines)

    def _build_system_prompt(
        self,
        agent_instructions: str,
        ctx: AgentContext,
        **extra: str,
    ) -> str:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(ctx.timezone)
        except Exception:
            from datetime import timezone as _tz
            tz = _tz.utc
        now = datetime.now(tz).strftime("%Y-%m-%d %H:%M %Z")
        datetime_line = f"Current date and time: {now}\n\n"

        identity_builder = ctx.identity_builder
        if identity_builder is not None:
            identity = identity_builder(
                ctx.persona,
                self._format_memory(ctx),
                profile=getattr(ctx.memory, "profile", None) if ctx.memory is not None else None,
                contacts_context=self._format_contacts(ctx),
            )
            prefix = f"{identity}\n\n"
        else:
            prefix = ""
        rendered = agent_instructions.format(**extra) if extra else agent_instructions
        return f"{datetime_line}{prefix}{rendered}"

    # ── Tool execution ────────────────────────────────────────────────────────

    async def call_tool(
        self,
        name: str,
        ctx: AgentContext,
        _iteration: int = -1,
        _lm_args: dict | None = None,
        **kwargs: Any,
    ) -> ToolCall:
        """Execute a registered tool with capability enforcement and hook dispatch.

        READ tools execute in any gate state.
        WRITE tools are suppressed and return a draft ToolCall when gate is DRAFT.
        Any tool raises ToolBlockedError when gate is BLOCKED.
        """
        from ze_agents.tool import get_tool

        spec = get_tool(name)

        if ctx.gate_decision == GateDecision.BLOCKED:
            raise ToolBlockedError(f"Tool {name!r} is blocked by the capability gate")

        stored_args = _lm_args if _lm_args is not None else kwargs

        if spec.access.value == "write" and ctx.gate_decision == GateDecision.DRAFT:
            log.info("tool_suppressed_draft", tool=name, agent=self.name)
            return ToolCall(
                tool_name=name,
                args=stored_args,
                result=None,
                duration_ms=0,
                success=False,
                error="suppressed: draft mode",
                is_draft=True,
            )

        # ── Hook: before ─────────────────────────────────────────────────────
        hooks = get_hooks()
        args: dict[str, Any] = dict(kwargs)
        for hook in hooks:
            try:
                modified = await hook.on_tool_start(
                    ToolStartEvent(name, args, ctx, _iteration)
                )
                if modified is not None:
                    args = modified
            except HookAbort as e:
                log.info("tool_skipped_by_hook", tool=name, agent=self.name, reason=e.reason)
                return ToolCall(
                    tool_name=name,
                    args=stored_args,
                    result=None,
                    duration_ms=0,
                    success=False,
                    error=f"skipped: {e.reason}",
                )
            except Exception as exc:
                log.warning("hook_error_on_tool_start", tool=name, agent=self.name, error=str(exc))

        # ── Execute ───────────────────────────────────────────────────────────
        log.debug("tool_start", tool=name, agent=self.name, access=spec.access.value)
        start = time.monotonic()
        try:
            result = await spec.func(**args)
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("tool_error", tool=name, agent=self.name, error=str(exc))
            tool_call = ToolCall(
                tool_name=name,
                args=stored_args,
                result=None,
                duration_ms=duration_ms,
                success=False,
                error=str(exc),
            )
            await _dispatch_tool_end(hooks, name, tool_call, ctx, _iteration)
            return tool_call

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("tool_complete", tool=name, agent=self.name, duration_ms=duration_ms)
        tool_call = ToolCall(
            tool_name=name,
            args=stored_args,
            result=result,
            duration_ms=duration_ms,
            success=True,
        )

        # ── Hook: after ───────────────────────────────────────────────────────
        await _dispatch_tool_end(hooks, name, tool_call, ctx, _iteration)
        return tool_call

    # ── Agentic loop ──────────────────────────────────────────────────────────

    async def agentic_loop(
        self,
        ctx: AgentContext,
        client: LLMClient,
        messages: list[dict],
        system: str,
        deps: dict[str, Any] | None = None,
        tool_names: list[str] | None = None,
        max_iterations: int = 6,
        max_history_tokens: int | None = None,
        max_tokens: int = 2000,
    ) -> tuple[str, list[ToolCall]]:
        """Drive a ReAct loop: LLM picks tools, ze dispatches them, repeat until text."""
        from ze_agents.delegate import (
            DELEGATE_TOOL_NAME,
            DELEGATE_TOOL_SCHEMA,
            run_delegate,
        )
        from ze_agents.tool import get_tool

        names = tool_names if tool_names is not None else self.tools
        tool_schemas = [
            _OPENROUTER_TOOL_SCHEMAS[n] if n in _OPENROUTER_TOOL_SCHEMAS
            else DELEGATE_TOOL_SCHEMA if n == DELEGATE_TOOL_NAME
            else get_tool(n).llm_schema()
            for n in names
        ]
        accumulated: list[ToolCall] = []
        _deps = deps or {}
        hooks = get_hooks()

        await _dispatch_loop_hooks(hooks, "on_loop_start", LoopStartEvent(self.name, ctx))

        # Fetch tool-executor memory context for direct invocations (e.g. from GoalExecutor)
        # that bypass the fetch_context graph node. Prepend as a context block to system.
        tool_ctx_block = await _fetch_tool_executor_context(ctx)
        if tool_ctx_block:
            system = f"{system}\n\n{tool_ctx_block}"

        for iteration in range(max_iterations):
            if ctx.abort_token is not None and ctx.abort_token.is_set:
                raise AgentAbortedError(ctx.abort_token.reason)

            if max_history_tokens is not None:
                _truncate_messages(messages, max_history_tokens)

            text, tool_calls = await client.complete_with_tools(
                messages=messages,
                model=ctx.model or self.model,
                tools=tool_schemas,
                system=system,
                max_tokens=max_tokens,
            )

            if text:
                log.debug(
                    "agentic_loop_done",
                    agent=self.name,
                    iterations=iteration + 1,
                    tool_calls=len(accumulated),
                )
                await _dispatch_loop_hooks(
                    hooks, "on_loop_end",
                    LoopEndEvent(self.name, ctx, accumulated, iterations_used=iteration + 1),
                )
                return text, accumulated

            if tool_calls is None:
                raise AgentError(
                    f"complete_with_tools returned no text and no tool calls "
                    f"(iteration {iteration + 1})"
                )

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                if _is_openrouter_server_tool(tc["name"]):
                    canonical = _canonical_openrouter_tool_name(tc["name"])
                    tool_call = ToolCall(
                        tool_name=canonical,
                        args=tc["arguments"],
                        result="[handled by OpenRouter]",
                        duration_ms=0,
                        success=True,
                    )
                    accumulated.append(tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "[search complete]",
                    })
                elif tc["name"] == DELEGATE_TOOL_NAME:
                    tool_call = await run_delegate(tc["arguments"], ctx, iteration)
                    accumulated.append(tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _serialise_result(tool_call),
                    })
                else:
                    merged = _merge_deps(tc["name"], tc["arguments"], _deps)
                    tool_call = await self.call_tool(
                        tc["name"], ctx, _iteration=iteration,
                        _lm_args=tc["arguments"], **merged,
                    )
                    accumulated.append(tool_call)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": _serialise_result(tool_call),
                    })

        log.warning("agentic_loop_max_iterations", agent=self.name, max_iterations=max_iterations)
        await _dispatch_loop_hooks(
            hooks, "on_loop_end",
            LoopEndEvent(self.name, ctx, accumulated, iterations_used=max_iterations),
        )
        text = await client.complete(
            messages=messages,
            model=ctx.model or self.model,
            system=system,
            max_tokens=max_tokens,
        )
        return text, accumulated


# ── Module-level helpers ──────────────────────────────────────────────────────

async def _dispatch_loop_hooks(hooks: list, method: str, event: Any) -> None:
    """Dispatch a loop lifecycle hook to all registered hooks."""
    for hook in hooks:
        try:
            await getattr(hook, method)(event)
        except AgentAbortedError:
            raise
        except Exception as exc:
            log.warning("hook_error", hook_method=method, error=str(exc))


async def _dispatch_tool_end(
    hooks: list,
    name: str,
    tool_call: ToolCall,
    ctx: AgentContext,
    iteration: int,
) -> None:
    for hook in hooks:
        try:
            await hook.on_tool_end(ToolEndEvent(name, tool_call, ctx, iteration))
        except Exception as exc:
            log.warning("hook_error_on_tool_end", tool=name, error=str(exc))

def _merge_deps(tool_name: str, llm_args: dict, deps: dict[str, Any]) -> dict:
    """Inject internal deps into tool kwargs for params the LLM cannot provide."""
    import inspect
    from ze_agents.tool import get_tool

    if _is_openrouter_server_tool(tool_name):
        return dict(llm_args)

    spec = get_tool(tool_name)
    merged = dict(llm_args)
    for param_name in inspect.signature(spec.func).parameters:
        if param_name not in merged and param_name in deps:
            merged[param_name] = deps[param_name]
    return merged


def _serialise_result(tc: ToolCall) -> str:
    if not tc.success:
        return f"[error: {tc.error}]"
    if tc.result is None:
        return "[no result]"
    if isinstance(tc.result, str):
        return tc.result
    try:
        return json.dumps(tc.result)
    except (TypeError, ValueError):
        return str(tc.result)


async def _fetch_tool_executor_context(ctx: Any) -> str:
    """Fetch facts + task state via ToolExecutorPolicy for direct agent invocations.

    Only runs when ctx.memory_store is set (goal executor path). Returns a formatted
    context block for prepending to the system prompt, or empty string if nothing
    is available.
    """
    store = getattr(ctx, "memory_store", None)
    if store is None:
        return ""
    try:
        import types as _types
        from uuid import UUID

        goal_id_str = ctx.extensions.get("goal_id") if ctx.extensions else None
        goal_id = UUID(goal_id_str) if goal_id_str else None

        # Use ctx.embed_fn if available (injected by container); fall back to None
        # so the retrieve call still works with stores that accept no embedding.
        embed_fn = getattr(ctx, "embed_fn", None)
        embedding = embed_fn(ctx.prompt) if embed_fn is not None else None

        request = _types.SimpleNamespace(
            module="tool_executor",
            agent="tool_executor",
            query_text=ctx.prompt,
            query_embedding=embedding,
            intent=ctx.intent,
            task_id=None,
            goal_id=goal_id,
            max_tokens=800,
        )
        memory_ctx = await store.retrieve(request)
    except Exception as exc:
        log.warning("tool_executor_context_fetch_failed", error=str(exc))
        return ""

    lines: list[str] = []
    facts = getattr(memory_ctx, "facts", [])
    if facts:
        lines.append("## Relevant facts")
        lines.extend(f"- {f.predicate}: {f.value}" for f in facts)
    task_state = getattr(memory_ctx, "task_state", None)
    if task_state is not None:
        lines.append("## Current task state")
        lines.append(f"Status: {task_state.status}")
        if task_state.open_steps:
            lines.append("Open steps: " + ", ".join(task_state.open_steps))
        if task_state.blocked_by:
            lines.append("Blocked by: " + ", ".join(task_state.blocked_by))
        if task_state.next_action:
            lines.append(f"Next action: {task_state.next_action}")
    return "\n".join(lines)


def _truncate_messages(messages: list[dict], max_tokens: int) -> None:
    """Remove oldest tool-call rounds until token estimate is under budget."""
    while True:
        total = sum(len(json.dumps(m)) // 4 for m in messages)
        if total <= max_tokens:
            break

        protected_from = max(0, len(messages) - 4)

        round_start = None
        for i in range(protected_from):
            if messages[i].get("role") == "assistant" and messages[i].get("tool_calls"):
                round_start = i
                break

        if round_start is None:
            break

        tool_call_ids = {tc["id"] for tc in messages[round_start]["tool_calls"]}
        indices_to_remove = [round_start]
        for j in range(round_start + 1, len(messages)):
            if messages[j].get("role") == "tool" and messages[j].get("tool_call_id") in tool_call_ids:
                indices_to_remove.append(j)
            elif messages[j].get("role") != "tool":
                break

        for idx in sorted(indices_to_remove, reverse=True):
            messages.pop(idx)
