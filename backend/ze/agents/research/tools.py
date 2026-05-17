import time

import structlog
from tavily import AsyncTavilyClient

from ze.agents.types import ToolCall

log = structlog.get_logger(__name__)


async def web_search(
    query: str,
    client: AsyncTavilyClient,
    max_results: int = 5,
) -> ToolCall:
    start = time.monotonic()
    try:
        result = await client.search(query, max_results=max_results)
        duration_ms = int((time.monotonic() - start) * 1000)
        return ToolCall(
            tool_name="web_search",
            args={"query": query, "max_results": max_results},
            result=result,
            duration_ms=duration_ms,
            success=True,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.warning("web_search_failed", query=query, error=str(exc))
        return ToolCall(
            tool_name="web_search",
            args={"query": query, "max_results": max_results},
            result=None,
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
        )


def format_search_results(tool_call: ToolCall) -> str:
    """Convert a Tavily search ToolCall result into a compact text block for the LLM."""
    if not tool_call.success or not tool_call.result:
        return "[search failed — no results available]"

    results = tool_call.result.get("results", [])
    if not results:
        return "[no search results found]"

    lines: list[str] = []
    for r in results:
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        content = r.get("content", "").strip()
        lines.append(f"**{title}**\n{url}\n{content}")

    return "\n\n---\n\n".join(lines)
