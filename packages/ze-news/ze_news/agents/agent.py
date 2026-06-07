from __future__ import annotations

from typing import AsyncIterator

import ze_news.agents.tools  # noqa: F401 — registers @tool decorators

from ze_core.capability.types import Mode
from ze_core.openrouter.client import OpenRouterClient
from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.orchestration.types import AgentContext, AgentResult

_AGENT_INSTRUCTIONS = """\
You are Ze's news capability. You answer questions about current events and headlines
using a local store of articles fetched from curated RSS sources.

Available tools:
- get_headlines: fetch recent headlines, optionally filtered by tag (global, local, tech, etc.)
- search_news: semantic search over stored articles by topic or keyword

Guidelines:
- Use get_headlines for broad digest queries ("what's in the news?", "any headlines today?").
- Use search_news when the user asks about a specific topic or event.
- Always include the article URL so the user can read more.
- For breaking news or specific facts that require up-to-date accuracy, tell the user
  that the local store may not reflect events from the last 30 minutes and suggest
  they ask Ze to search the web directly.
- Summarise concisely — one or two sentences per article is enough unless the user
  asks for more detail.\
"""


@agent
class NewsAgent(BaseAgent):
    name = "news"
    description = """
      Answers questions about current events and headlines using a curated local news store.
      Use for digest-style queries: "what's in the news?", "any tech headlines?",
      "what happened in Portugal this week?", "latest headlines", "news briefing".
      Do NOT use for breaking news fact-checks or queries requiring real-time accuracy
      — use the research agent with web search for those.
    """
    model = "openai/gpt-4o-mini"
    vision_capable = False
    timeout = 30
    tools = ["get_headlines", "search_news"]
    intent_map = {
        "read": "Retrieve and summarise news headlines or articles from the local store.",
    }
    capabilities = {
        "read": Mode.AUTONOMOUS,
    }

    def __init__(
        self,
        client: OpenRouterClient,
        **kwargs: object,
    ) -> None:
        super().__init__(client=client, **kwargs)

    def _build_system_prompt(self, ctx: AgentContext) -> str:
        return _AGENT_INSTRUCTIONS

    async def run(self, ctx: AgentContext) -> AgentResult:
        return await self._run_tool_loop(ctx, self._build_system_prompt(ctx))

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        async for chunk in self._stream_tool_loop(ctx, self._build_system_prompt(ctx)):
            yield chunk
