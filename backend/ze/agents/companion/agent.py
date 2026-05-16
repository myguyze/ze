from typing import AsyncIterator

from ze.agents.base import BaseAgent
from ze.agents.companion.prompt import SYSTEM_PROMPT
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.logging import get_logger
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings


@register
class CompanionAgent(BaseAgent):
    name = "companion"

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._client = openrouter_client
        self._settings = settings
        self._log = get_logger(__name__)

    def _model(self) -> str:
        return self._settings.agent_configs.get("companion", {}).get(
            "model", "anthropic/claude-sonnet-4-5"
        )

    def _system_prompt(self, ctx: AgentContext) -> str:
        memory_lines: list[str] = []
        for fact in ctx.memory.facts:
            memory_lines.append(f"- {fact.key}: {fact.value}")
        memory_context = "\n".join(memory_lines) if memory_lines else "(none)"
        return SYSTEM_PROMPT.format(memory_context=memory_context)

    async def run(self, ctx: AgentContext) -> AgentResult:
        messages = [{"role": "user", "content": ctx.prompt}]
        response = await self._client.complete(
            messages=messages,
            model=self._model(),
            system=self._system_prompt(ctx),
        )

        self._log.info(
            "companion_agent_complete",
            session_id=ctx.session_id,
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=[],
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        messages = [{"role": "user", "content": ctx.prompt}]
        async for token in self._client.stream(
            messages=messages,
            model=self._model(),
            system=self._system_prompt(ctx),
        ):
            yield token
