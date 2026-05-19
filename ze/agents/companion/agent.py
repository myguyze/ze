from typing import AsyncIterator

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.tools.facts import to_user_facts

_AGENT_INSTRUCTIONS = """\
You are Ze's companion and thinking partner. You reason from what you know and from what \
the user tells you — you do not search the web.

- Engage thoughtfully: reflect, explore ideas, and help the user think through problems.
- Be honest when you don't know something or when a question needs current data you lack.
- Match the user's energy: casual for casual topics, substantive when they need depth.\
"""


@register
class CompanionAgent(BaseAgent):
    name  = "companion"
    tools = ["extract_facts"]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        response = await self._client.complete(
            messages=ctx.messages,
            model=self._model(),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
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
            "companion_agent_complete",
            session_id=ctx.session_id,
            proposals=len(proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=[facts_tc],
            memory_proposals=proposals,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        async for token in self._client.stream(
            messages=ctx.messages,
            model=self._model(),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        ):
            yield token


