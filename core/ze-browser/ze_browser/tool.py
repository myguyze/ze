import asyncio
import time

from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.orchestration.types import ToolCall
from ze_browser.client import BrowserClient

_BLOCKED_MSG = "[blocked or empty — skip this URL]"


@tool(
    access=ToolAccess.READ,
    description=(
        "Navigate to a URL and return its visible text content. "
        "Returns an error string if the page is blocked or unreachable — "
        "in that case, skip this URL and try another source."
    ),
)
async def browser_extract(
    url: str,
    browser_client: BrowserClient,
    browser_delay_ms: int,
    browser_max_text_chars: int,
) -> ToolCall:
    await asyncio.sleep(browser_delay_ms / 1000)
    start = time.monotonic()
    try:
        result = await browser_client.extract(url)
        duration_ms = int((time.monotonic() - start) * 1000)

        if not result.text or result.status_code >= 400:
            return ToolCall(
                tool_name="browser_extract",
                args={"url": url},
                result=_BLOCKED_MSG,
                duration_ms=duration_ms,
                success=True,
            )

        text = result.text[:browser_max_text_chars]
        return ToolCall(
            tool_name="browser_extract",
            args={"url": url},
            result=text,
            duration_ms=duration_ms,
            success=True,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        return ToolCall(
            tool_name="browser_extract",
            args={"url": url},
            result=f"[error: {exc}]",
            duration_ms=duration_ms,
            success=False,
            error=str(exc),
        )
