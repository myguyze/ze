from typing import AsyncIterator
from uuid import UUID

import asyncpg

import ze.tools.browser  # noqa: F401 — registers browser_extract @tool
import ze.tools.prospecting  # noqa: F401 — registers add_prospect, draft_outreach @tool

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze_browser import BrowserClient
from ze.contacts.store import PersonStore
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings

_AGENT_INSTRUCTIONS = """\
You are Ze's prospecting engine. Given a brief, you autonomously:
1. Research candidates matching the target profile using the tools below.
2. Enrich each candidate: name, role, company, email, LinkedIn URL.
3. Add each via add_prospect — include enrichment_notes summarising what you found
   and what's missing. This surfaces quality to the user.
4. Generate the output the user requested (summary, draft outreach, or both).

Research strategy — work through sources in this priority order:
- web_search: identify companies in the target space, then find people at those companies
- browser_extract on company websites: team/about pages often list names and roles
- browser_extract on government/industry registries: ANAC (aviation), RNPC (companies),
  sector-specific databases — search for these via web_search first
- LinkedIn public profiles: Google "site:linkedin.com/in [name] [title] [country]",
  then browser_extract the result URL

If browser_extract returns "[blocked or empty]", move to the next source immediately.
Do not retry the same URL more than once.

Stop when you reach the requested count or have exhausted reasonable sources.

Final output format:
- Summary: for each prospect — name, company, role, contact info found, and a one-line
  enrichment note ("email found", "LinkedIn only", "name and company only — sparse").
- Drafts (if requested): one message per prospect after the summary.
"""


@register
class ProspectingAgent(BaseAgent):
    name = "prospecting"
    tools = [
        "web_search",
        "browser_extract",
        "add_prospect",
        "draft_outreach",
    ]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        settings: Settings,
        browser_client: BrowserClient,
        person_store: PersonStore,
        pool: asyncpg.Pool,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._browser_client = browser_client
        self._person_store = person_store
        self._pool = pool

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "prospecting.researching")

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO prospect_campaigns (brief, status)
                VALUES ($1, 'running')
                RETURNING id
                """,
                ctx.prompt,
            )
        campaign_id: UUID = row["id"]

        reachable = await self._browser_client.health()
        if not reachable:
            self._log.warning("browser_service_unreachable", campaign_id=str(campaign_id))

        tool_names = (
            self.tools
            if reachable
            else [t for t in self.tools if t != "browser_extract"]
        )

        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        deps = {
            "browser_client": self._browser_client,
            "person_store": self._person_store,
            "pool": self._pool,
            "client": self._client,
            "model": self._model(ctx),
            "settings": self._settings,
            "campaign_id": str(campaign_id),
        }

        try:
            response, tool_calls = await self.agentic_loop(
                ctx,
                client=self._client,
                messages=list(ctx.messages),
                system=system,
                deps=deps,
                tool_names=tool_names,
                max_iterations=self._settings.prospecting_max_iterations,
                max_history_tokens=self._settings.prospecting_max_loop_tokens,
                max_tokens=4000,
            )

            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE prospect_campaigns
                    SET status = 'complete', output = $2, completed_at = NOW()
                    WHERE id = $1
                    """,
                    campaign_id,
                    response,
                )

            return AgentResult(
                agent=self.name,
                response=response,
                tool_calls=tool_calls,
            )
        except Exception:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE prospect_campaigns
                    SET status = 'failed', completed_at = NOW()
                    WHERE id = $1
                    """,
                    campaign_id,
                )
            raise

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        raise NotImplementedError("ProspectingAgent does not support streaming")
        yield  # make mypy happy
