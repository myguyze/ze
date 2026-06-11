from typing import AsyncIterator

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.openrouter.client import OpenRouterClient
from ze_core.settings import Settings
from ze_core.capability.types import Mode

_AGENT_INSTRUCTIONS = """\
You are Ze's research capability. Use web search to find accurate, up-to-date information.

- Always search before answering questions about current events, facts, or anything that may have changed.
- Summarize sources clearly and cite them when relevant.
- If search results are insufficient, say so rather than guessing.
- Never fabricate URLs or quotes.
- If the question requires calendar data (e.g. "when am I free?", "what's on my schedule?"), \
delegate to the calendar agent using delegate_to_agent rather than guessing.\
"""


@agent
class ResearchAgent(BaseAgent):
    name = "research"
    description = """
      Handles web searches, fact-finding, summarisation, and research synthesis.
      Use when the user explicitly says "research", "look up", "find out", "search for",
      or asks about current events, factual lookups, topic deep-dives, company or
      organisation history, news, or anything requiring information retrieval from the web.
      Also use for factual comparisons ("what are the differences between X and Y"),
      technical how-things-work questions, and any query where accurate sourced information
      matters more than reasoning or conversation.
    """
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    tools = ["openrouter:web_search", "delegate_to_agent"]
    intent_map = {"read": "openrouter:web_search"}
    capabilities = {
        "read": Mode.AUTONOMOUS,
        "execute": Mode.CONFIRM,
        "create": Mode.AUTONOMOUS,
        "update": Mode.AUTONOMOUS,
        "delete": Mode.AUTONOMOUS,
        "reason": Mode.AUTONOMOUS,
    }

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "research.searching")
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
        )

        search_count = len([tc for tc in loop_tool_calls if tc.tool_name == "openrouter:web_search"])

        self._log.info(
            "research_agent_complete",
            session_id=ctx.session_id,
            search_count=search_count,
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=loop_tool_calls,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        model = self._model(ctx)
        if not model.endswith(":online"):
            model = f"{model}:online"
        async for token in self._client.stream(
            messages=ctx.messages,
            model=model,
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        ):
            yield token
