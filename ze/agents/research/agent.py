from typing import AsyncIterator

from tavily import AsyncTavilyClient

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.research.prompt import SYSTEM_PROMPT
from ze.agents.research.tools import format_search_results
from ze.agents.types import AgentContext, AgentResult
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.tools.facts import to_user_facts


@register
class ResearchAgent(BaseAgent):
    name  = "research"
    tools = ["web_search", "extract_facts"]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        tavily_client: AsyncTavilyClient,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._tavily = tavily_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        search_tc = await self.call_tool(
            "web_search", ctx, query=ctx.prompt, client=self._tavily
        )

        augmented = f"{ctx.prompt}\n\nSearch results:\n{format_search_results(search_tc)}"
        response = await self._client.complete(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(),
            system=SYSTEM_PROMPT.format(memory_context=self._format_memory(ctx)),
        )

        facts_tc = await self.call_tool(
            "extract_facts", ctx,
            prompt=ctx.prompt,
            response=response,
            client=self._client,
            model=self._model(),
        )

        proposals = to_user_facts(facts_tc.result or [])

        self._log.info(
            "research_agent_complete",
            session_id=ctx.session_id,
            search_success=search_tc.success,
            proposals=len(proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=[search_tc, facts_tc],
            memory_proposals=proposals,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        search_tc = await self.call_tool(
            "web_search", ctx, query=ctx.prompt, client=self._tavily
        )
        augmented = f"{ctx.prompt}\n\nSearch results:\n{format_search_results(search_tc)}"
        async for token in self._client.stream(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(),
            system=SYSTEM_PROMPT.format(memory_context=self._format_memory(ctx)),
        ):
            yield token


