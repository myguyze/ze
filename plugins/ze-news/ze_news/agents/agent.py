from __future__ import annotations

from typing import AsyncIterator

import ze_news.agents.tools  # noqa: F401 — registers @tool decorators

from ze_agents.types import Mode
from ze_memory.retriever import PostgresMemoryStore
from ze_core.openrouter.client import OpenRouterClient
from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import AgentContext, AgentResult
from ze_news.store import NewsStore
from ze_news.types import GoalTitleProvider, PersonalizationContext

_AGENT_INSTRUCTIONS = """\
You are Ze's news capability. You answer questions about current events and headlines
using a local store of articles fetched from curated RSS sources.

Available tools:
- get_headlines: fetch recent headlines personalised to your interests, optionally filtered
  by tag (global, local, tech, etc.). Returns two buckets: 'relevant' (ranked by your
  interests) and 'discovery' (fresh, off-profile articles). Present both sections to the user.
- search_news: semantic search over stored articles by topic or keyword

Guidelines:
- Use get_headlines for broad digest queries ("what's in the news?", "any headlines today?").
- Use search_news when the user asks about a specific topic or event.
- When presenting get_headlines results, show 'relevant' articles first under "📰 For you:"
  and 'discovery' articles under "🔭 Outside your usual:" if the discovery bucket is non-empty.
- Always include the article URL so the user can read more.
- For breaking news or specific facts that require up-to-date accuracy, tell the user
  that the local store may not reflect events from the last 30 minutes and suggest
  they ask Ze to search the web directly.
- Summarise concisely — one or two sentences per article is enough unless the user
  asks for more detail.\
"""

_EXCLUSION_KEYS = ("not interested", "don't like", "avoid", "no ")


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
        memory_store: PostgresMemoryStore,
        goal_provider: GoalTitleProvider,
        news_store: NewsStore,
    ) -> None:
        self._client = client
        self._memory_store = memory_store
        self._goal_provider = goal_provider
        self._news_store = news_store

    async def run(self, ctx: AgentContext) -> AgentResult:
        personalization_ctx = await self._build_personalization_ctx()
        deps = {
            "news_store": self._news_store,
            "_personalization_ctx": personalization_ctx,
        }
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps=deps,
        )
        return AgentResult(agent=self.name, response=response, tool_calls=tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        personalization_ctx = await self._build_personalization_ctx()
        deps = {
            "news_store": self._news_store,
            "_personalization_ctx": personalization_ctx,
        }
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        messages = list(ctx.messages)
        tool_names = list(self.tools)
        # stream is not supported via agentic_loop — fall back to a single completion
        response, _ = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=messages,
            system=system,
            deps=deps,
            tool_names=tool_names,
        )
        yield response

    async def _build_personalization_ctx(self) -> PersonalizationContext:
        try:
            facts = await self._memory_store.list_recent_facts(days=90, limit=30)
        except Exception:
            facts = []

        try:
            goals = await self._goal_provider.list_active_goal_titles()
        except Exception:
            goals = []

        exclusions = [
            f.value for f in facts
            if any(kw in f.predicate.lower() for kw in _EXCLUSION_KEYS)
        ]
        topic_facts = [f for f in facts if f.value not in exclusions]
        interest_parts = [f"{f.predicate}: {f.value}" for f in topic_facts]
        interest_parts += goals

        return PersonalizationContext(
            interest_text=" | ".join(interest_parts),
            exclusions=exclusions,
            fact_count=len(topic_facts),
        )
