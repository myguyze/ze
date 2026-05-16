from typing import AsyncIterator

from tavily import AsyncTavilyClient

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.research.prompt import SYSTEM_PROMPT
from ze.agents.research.tools import format_search_results, web_search
from ze.agents.types import AgentContext, AgentResult
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings


@register
class ResearchAgent(BaseAgent):
    name = "research"

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        tavily_client: AsyncTavilyClient,
        settings: Settings,
    ) -> None:
        self._client = openrouter_client
        self._tavily = tavily_client
        self._settings = settings
        self._log = get_logger(__name__)

    def _model(self) -> str:
        return self._settings.agent_configs.get("research", {}).get(
            "model", "anthropic/claude-sonnet-4-5"
        )

    def _timeout(self) -> int:
        return int(self._settings.agent_configs.get("research", {}).get("timeout", 30))

    def _system_prompt(self, ctx: AgentContext) -> str:
        memory_lines: list[str] = []
        for fact in ctx.memory.facts:
            memory_lines.append(f"- {fact.key}: {fact.value}")
        memory_context = "\n".join(memory_lines) if memory_lines else "(none)"
        return SYSTEM_PROMPT.format(memory_context=memory_context)

    async def run(self, ctx: AgentContext) -> AgentResult:
        search_tc = await web_search(ctx.prompt, self._tavily)
        tool_calls = [search_tc]

        search_block = format_search_results(search_tc)
        augmented_prompt = f"{ctx.prompt}\n\nSearch results:\n{search_block}"

        messages = [{"role": "user", "content": augmented_prompt}]
        response = await self._client.complete(
            messages=messages,
            model=self._model(),
            system=self._system_prompt(ctx),
        )

        self._log.info(
            "research_agent_complete",
            session_id=ctx.session_id,
            search_success=search_tc.success,
            search_duration_ms=search_tc.duration_ms,
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=tool_calls,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        search_tc = await web_search(ctx.prompt, self._tavily)

        search_block = format_search_results(search_tc)
        augmented_prompt = f"{ctx.prompt}\n\nSearch results:\n{search_block}"

        messages = [{"role": "user", "content": augmented_prompt}]
        async for token in self._client.stream(
            messages=messages,
            model=self._model(),
            system=self._system_prompt(ctx),
        ):
            yield token
