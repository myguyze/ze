# Agentic Tool Loop — Spec

## Implementation Status

| Feature | Status |
|---------|--------|
| `ToolSpec.llm_schema()` — OpenAI-format function schema | ✅ Done |
| `BaseAgent.agentic_loop()` — ReAct loop with tool dispatch | ✅ Done |
| Ze-internal dep injection via `_merge_deps` | ✅ Done |
| Gate enforcement inside loop (draft / blocked) | ✅ Done |
| Max-iterations fallback to plain completion | ✅ Done |
| Calendar agent migrated to agentic loop | ✅ Done |
| Email agent migrated to agentic loop | ✅ Done |

## Purpose

Allow agents to expose tools to the LLM and let the model decide which tools to
call, how many times, and in what order — rather than having the agent hardcode a
fixed tool sequence. The LLM drives the loop; Ze enforces gates and injects
infrastructure dependencies.

## Problem with the current model

Every agent today hand-wires its tool sequence:

```python
# research agent — always exactly one search, regardless of result quality
search_tc  = await self.call_tool("web_search", ctx, query=ctx.prompt, ...)
response   = await self._client.complete(augmented, ...)
# fact extraction runs in write_memory — not in the agent run() path
```

If the first search is shallow the agent cannot search again. If the prompt only
needs half the tools the agent still runs all of them.

## Solution

Add two primitives:

1. **`ToolSpec.llm_schema()`** — generates the OpenAI-format function schema for a
   tool, automatically excluding parameters that are Ze-internal (not JSON-primitive).
2. **`BaseAgent.agentic_loop()`** — drives a ReAct loop: call LLM with tool schemas
   → if tool calls, dispatch via `call_tool()` + inject deps → loop until text
   response or max iterations.

Agents opt in by calling `agentic_loop()` instead of manually orchestrating tools.
Existing agents that do not call `agentic_loop()` are unaffected.

## `ToolSpec.llm_schema()`

`ze/agents/tool.py`

Returns a dict in OpenAI function-calling format:

```python
{
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information via Tavily.",
        "parameters": {
            "type": "object",
            "properties": {
                "query":       {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
}
```

**LLM-visible params**: only params whose type annotation is JSON-primitive
(`str`, `int`, `float`, `bool`, `None`, `Any`, `list[…]`, `dict`, or `Optional`
of these). Params typed as domain objects (e.g. `AsyncTavilyClient`,
`OpenRouterClient`) are excluded — Ze injects those at call time.

**Type mapping**:

| Python annotation | JSON Schema type |
|---|---|
| `str` | `"string"` |
| `int` | `"integer"` |
| `float` | `"number"` |
| `bool` | `"boolean"` |
| `list[…]` / `List[…]` | `"array"` |
| `dict` / `Dict` | `"object"` |
| `Optional[X]` | type of `X` (non-required) |
| `Any` | `"string"` |

**Required params**: a param is required if it has no default AND its type is not
`Optional[…]`. Params with defaults or typed as `Optional` are omitted from
`required`.

## `OpenRouterClient.complete_with_tools()`

`ze/openrouter/client.py`

```python
async def complete_with_tools(
    self,
    messages: list[dict],
    model: str,
    tools: list[dict],         # list of llm_schema() dicts
    system: str | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
) -> tuple[str | None, list[dict] | None]:
```

Returns exactly one of:
- `(text, None)` — model produced a text response; no tool calls.
- `(None, tool_call_list)` — model wants to call tools.

Each item in `tool_call_list` is:

```python
{
    "id":        "call_abc123",   # opaque string, used as tool_call_id in replies
    "name":      "web_search",
    "arguments": {"query": "..."},  # parsed dict, not the raw JSON string
}
```

Uses the same retry/backoff logic as `complete()`. Does not support streaming
(tool-use loops are inherently sequential).

## `BaseAgent.agentic_loop()`

`ze/agents/base.py`

```python
async def agentic_loop(
    self,
    ctx: AgentContext,
    client: OpenRouterClient,
    messages: list[dict],
    system: str,
    deps: dict[str, Any],
    tool_names: list[str] | None = None,
    max_iterations: int = 6,
) -> tuple[str, list[ToolCall]]:
```

**Parameters:**

| Parameter | Purpose |
|---|---|
| `ctx` | Current agent context — passed to `call_tool()` for gate enforcement |
| `client` | OpenRouter client for LLM calls |
| `messages` | Conversation messages (including the current user turn); mutated in-place as tool turns are appended |
| `system` | System prompt |
| `deps` | Ze-internal deps available for injection (e.g. `{"client": tavily_client}`) |
| `tool_names` | Which tools to expose to the LLM; defaults to `self.tools` |
| `max_iterations` | Maximum tool-call rounds before forcing a plain completion |

**Loop behaviour:**

```
for i in range(max_iterations):
    text, tool_calls = await client.complete_with_tools(messages, model, tools, system)

    if text is not None:
        return text, accumulated_tool_calls

    # Append assistant message + tool results, continue
    messages.append(assistant_tool_call_message)
    for tc in tool_calls:
        tool_call = await self.call_tool(tc["name"], ctx, **_merge(tc["arguments"], deps, spec))
        messages.append(tool_result_message(tc["id"], tool_call))
        accumulated_tool_calls.append(tool_call)

# Force a final text response (tools no longer offered)
text = await client.complete(messages, model, system)
return text, accumulated_tool_calls
```

**Dep injection**: for each tool the LLM requests, the loop looks up the tool's
`ToolSpec.params`, identifies params not provided by the LLM (i.e. not in
`tc["arguments"]`), and fills them from `deps` by param name. Unknown params that
are also not in `deps` cause a `ZeError` at runtime.

**Tool result formatting**: `ToolCall.result` is JSON-serialised when it is a dict
or list; string results are passed as-is. Failed tool calls produce
`[error: <message>]` — the LLM can react by retrying or giving up.

**Gate enforcement**: `call_tool()` already enforces the capability gate. The loop
adds no extra gate logic.

## Updating ResearchAgent

`ze/agents/research/agent.py`

`run()` becomes:

```python
async def run(self, ctx: AgentContext) -> AgentResult:
    await self.emit(ctx, "research.searching")
    response, tool_calls = await self.agentic_loop(
        ctx,
        client=self._client,
        messages=list(ctx.messages),
        system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        deps={"client": self._tavily},
        tool_names=["web_search"],
    )
    await self.emit(ctx, "research.summarising")
    return AgentResult(
        agent=self.name,
        response=response,
        tool_calls=tool_calls,
    )
```

The LLM may now issue multiple `web_search` calls if the first result is
insufficient, summarise them, and return. User-fact extraction runs in
`write_memory` via `ze_core.memory.extractor`, not in the agent loop.

`stream()` is unchanged — it remains a fixed-sequence fallback for streaming
contexts, which do not support tool-call loops.

## What does NOT change

- `AgentState`, graph nodes, edges, orchestration — no changes.
- `call_tool()` in `BaseAgent` — no changes.
- Capability gate enforcement — unchanged, still inside `call_tool()`.
- All other agents (companion, calendar, email, workflow, reminders) — unchanged
  until individually opted in.

## Future adoption

Any agent can opt in by calling `agentic_loop()`. Suggested candidates:

- **calendar** — let the LLM decide whether to list events, create one, or both.
- **workflow** — let the LLM adaptively plan steps by querying context tools.

## Open Questions

All resolved.
