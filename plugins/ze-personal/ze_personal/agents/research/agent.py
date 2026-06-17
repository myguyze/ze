from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import AgentContext, AgentResult
from ze_agents.client import LLMClient
from ze_agents.settings import Settings
from ze_agents.types import Intent, Mode

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
    display_name = "Web research"
    description = """
      Web search and technical fact-finding using live information retrieval.
      Use for: factual comparisons ("what are the differences between X and Y"),
      technical deep-dives ("how does async/await work", "how does X work internally"),
      coding questions ("how do I implement X in Python", "why does X happen in JavaScript"),
      "look up X", "search for X", "find out about X", "what is X", recent events
      needing accurate sourced answers, and any query requiring verified facts from the web.
      Not for calendar, email, reminders, or news digest summaries.
    """
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    tools = ["openrouter:web_search", "delegate_to_agent"]
    intents = {
        "read": Intent(Mode.AUTONOMOUS, "Search the web and retrieve information."),
    }
    default_mode = Mode.AUTONOMOUS

    def __init__(
        self,
        openrouter_client: LLMClient,
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
