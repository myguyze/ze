from __future__ import annotations

from datetime import date, timezone
from typing import AsyncIterator

import ze_news.agents.tools  # noqa: F401 — registers @tool decorators

from ze_agents.types import Mode
from ze_sdk.memory import PostgresMemoryStore
from ze_agents.client import LLMClient
from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.settings import Settings as CoreSettings
from ze_agents.types import AgentContext, AgentResult, ToolCall
from ze_news.jobs.fetch import NewsFetchJob
from ze_news.preferences import NewsPreferenceBuilder, is_diagnostic_query
from ze_news.store import NewsStore
from ze_news.types import GoalTitleProvider, PersonalizationContext, PersonalizationSettings

_AGENT_INSTRUCTIONS = """\
You are Ze's news capability. You answer questions about current events and headlines
using a local store of articles fetched from curated RSS sources.

Store freshness: {store_freshness_note}

Candidate articles already retrieved from the local store for this request:
{candidate_articles}

Available tools:
- refresh_news: trigger an immediate RSS fetch from all sources, bypassing the 30-minute
  interval. Only call this when the store freshness note says it is NOT fresh and the
  candidate list is empty or outdated. After it returns, call get_headlines.
- get_headlines: fetch recent headlines personalised to your interests, optionally filtered
  by tag (global, local, tech, etc.). Returns two buckets: 'relevant' (ranked by your
  interests) and 'discovery' (fresh, off-profile articles). Present both sections to the user.
- search_news: semantic search over stored articles by topic or keyword

Grounding rules (these override everything else):
- Every headline, fact, or claim you present MUST come from the candidate articles above
  or from a tool result. NEVER invent, embellish, or recall headlines from your own
  knowledge.
- Always cite each article with its source, published date, and URL.
- ONLY call refresh_news when the store freshness note explicitly says the store is NOT
  fresh. If the note says the store IS fresh, skip refresh_news and call get_headlines
  directly — even if the user says "more recent" or "today's news". A fresh store
  already has today's articles; calling refresh_news again wastes time and returns the
  same articles.
- If the store is fresh but get_headlines still returns nothing, tell the user the store
  has no matching articles and offer to have Ze's research agent search the web instead.
  Do not fabricate a digest.
- If asked how you obtained the news or whether it is recent, explain that it comes
  from the local store of curated RSS articles and use the published dates above.

Guidelines:
- Use get_headlines for broad digest queries ("what's in the news?", "any headlines today?",
  "more news", "show me more", "latest news").
- Use search_news when the user asks about a specific topic or event.
- When presenting headlines, aim for 8–12 articles in total. Do not arbitrarily stop at
  4 or 5 — present a proper digest. Show 'relevant' articles first under "📰 For you:"
  and 'discovery' articles under "🔭 Outside your usual:" if the discovery bucket is
  non-empty.
- Do not infer that the user wants more coverage of a topic just because they ask why it
  was shown. Treat "why did you show X?", "stop showing X" as diagnostics or preference
  management.
- For breaking news or specific facts that require up-to-date accuracy, tell the user
  that the local store may not reflect events from the last 30 minutes and suggest
  they ask Ze to search the web directly.
- Summarise concisely — one or two sentences per article is enough unless the user
  asks for more detail.\
"""

_CANDIDATE_LIMIT = 8


def _format_candidates(articles: list) -> str:
    if not articles:
        return "(none — the local store returned no articles for this query)"
    lines = []
    for a in articles:
        lines.append(
            f"- {a.title} | source: {a.source_key} | "
            f"published: {a.published_at.isoformat()} | {a.url}"
        )
    return "\n".join(lines)


def _freshness_note(candidates: list) -> str:
    today = date.today()
    for article in candidates:
        pub = article.published_at
        if hasattr(pub, "tzinfo") and pub.tzinfo is not None:
            pub_date = pub.astimezone(timezone.utc).date()
        else:
            pub_date = pub.date()
        if pub_date >= today:
            return (
                f"FRESH — the store contains articles published today ({today}). "
                "Do NOT call refresh_news."
            )
    if candidates:
        latest = max(a.published_at for a in candidates)
        return (
            f"POSSIBLY STALE — the newest candidate article is from "
            f"{latest.date()}. Consider calling refresh_news if the user "
            "expects today's headlines."
        )
    return "UNKNOWN — no candidates retrieved; call refresh_news then get_headlines."


@agent
class NewsAgent(BaseAgent):
    name = "news"
    display_name = "News"
    description = """
      News headlines and daily briefings from curated sources.
      Use for: "what's in the news today", "any headlines", "morning news briefing",
      "latest news", "news digest", "what's happening in the world", "tech news today",
      "give me a news summary", "what's trending", "top stories today".
      For news digest and headline summaries only — not for factual research or web search.
    """
    model = "openai/gpt-4o-mini"
    vision_capable = False
    timeout = 30
    tools = ["refresh_news", "get_headlines", "search_news"]
    intent_map = {
        "read": "Retrieve and summarise news headlines or articles from the local store.",
    }
    capabilities = {
        "read": Mode.AUTONOMOUS,
    }

    def __init__(
        self,
        client: LLMClient,
        memory_store: PostgresMemoryStore,
        goal_provider: GoalTitleProvider,
        news_store: NewsStore,
        news_fetch_job: NewsFetchJob,
        settings: CoreSettings,
    ) -> None:
        self._client = client
        self._memory_store = memory_store
        self._goal_provider = goal_provider
        self._news_store = news_store
        self._fetch_job = news_fetch_job
        self._personalization_settings = PersonalizationSettings.from_config(
            settings.config.get("news", {})
        )
        self._preference_builder = NewsPreferenceBuilder(
            memory_store=memory_store,
            goal_provider=goal_provider,
            fact_days=self._personalization_settings.fact_days,
            fact_limit=self._personalization_settings.fact_limit,
            min_confidence=self._personalization_settings.min_confidence,
            explore_ratio=self._personalization_settings.explore_ratio,
            max_per_topic=self._personalization_settings.max_per_topic,
            candidate_multiplier=self._personalization_settings.candidate_multiplier,
        )

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "news.reading")
        response, tool_calls = await self._grounded_loop(ctx)
        return AgentResult(agent=self.name, response=response, tool_calls=tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        # stream is not supported via agentic_loop — fall back to a single completion
        response, _ = await self._grounded_loop(ctx)
        yield response

    async def _grounded_loop(self, ctx: AgentContext) -> tuple[str, list[ToolCall]]:
        """Pre-fetch candidate articles so the answer is always grounded in the
        store, even when the model never calls a tool."""
        personalization_ctx = await self._build_personalization_ctx(ctx.prompt)
        candidates = await self._fetch_candidates(ctx.prompt)
        deps = {
            "news_store": self._news_store,
            "news_fetch_job": self._fetch_job,
            "reporter": ctx.reporter,
            "_personalization_ctx": personalization_ctx,
            "_diagnostic_query": is_diagnostic_query(ctx.prompt),
            "_min_preferences": self._personalization_settings.min_preferences,
        }
        system = self._build_system_prompt(
            _AGENT_INSTRUCTIONS,
            ctx,
            candidate_articles=_format_candidates(candidates),
            store_freshness_note=_freshness_note(candidates),
        )
        response, tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps=deps,
        )
        provenance = ToolCall(
            tool_name="search_news",
            args={"query": ctx.prompt, "limit": _CANDIDATE_LIMIT, "prefetched": True},
            result=[a.url for a in candidates],
            duration_ms=0,
            success=True,
        )
        return response, [provenance, *tool_calls]

    async def _fetch_candidates(self, prompt: str) -> list:
        try:
            return await self._news_store.search(prompt, limit=_CANDIDATE_LIMIT)
        except Exception as exc:
            self._log.warning("news_candidate_prefetch_failed", error=str(exc))
            return []

    async def _build_personalization_ctx(self, query_text: str) -> PersonalizationContext:
        return await self._preference_builder.build(query_text)
