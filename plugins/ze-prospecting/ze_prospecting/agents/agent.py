import ze_browser.tool  # noqa: F401 — registers browser_extract @tool
import ze_prospecting.agents.tools  # noqa: F401 — registers add_prospect, draft_outreach, log_outreach_event @tool

from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import Intent, Mode
from ze_agents.types import AgentContext, AgentResult
from ze_browser import BrowserClient
from ze_personal.contacts.store import PersonStore
from ze_agents.client import LLMClient
from ze_agents.settings import Settings
from ze_prospecting.store import ProspectCampaignStore
from ze_prospecting.types import ProspectingSettings

_AGENT_INSTRUCTIONS = """\
You are Ze's prospecting engine. Given a brief, you autonomously:
1. Research candidates matching the target profile using the tools below.
2. Enrich each candidate: name, role, company, email, LinkedIn URL.
3. Add each via add_prospect — include enrichment_notes summarising what you found
   and what's missing. This surfaces quality to the user.
4. Generate the output the user requested (summary, draft outreach, or both).

Research strategy — work through sources in this priority order:
- openrouter:web_search: identify companies in the target space, then find people at those companies
- browser_extract on company websites: team/about pages often list names and roles
- browser_extract on government/industry registries: ANAC (aviation), RNPC (companies),
  sector-specific databases — search for these via openrouter:web_search first
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


@agent
class ProspectingAgent(BaseAgent):
    name = "prospecting"
    display_name = "Prospecting"
    description = """
      Sales prospecting, lead research, and outreach campaign materials.
      Use for: "find leads in the X industry", "prospect for customers in Y",
      "build a target list of companies in Z", "research potential clients",
      "draft outreach email for X company", "qualify this lead", "enrich contact details",
      "start a prospecting campaign", "find contacts at X". Not for general web research.
    """
    model = "anthropic/claude-sonnet-4-5"
    timeout = 180
    tools = [
        "openrouter:web_search",
        "browser_extract",
        "add_prospect",
        "draft_outreach",
        "log_outreach_event",
    ]
    intents = {
        "read": Intent(Mode.AUTONOMOUS, "Research and enrich prospect candidates"),
        "write": Intent(Mode.AUTONOMOUS, "Draft outreach for prospects"),
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        settings: Settings,
        prospecting_settings: ProspectingSettings,
        browser_client: BrowserClient,
        person_store: PersonStore,
        campaign_store: ProspectCampaignStore,
    ) -> None:
        self._settings = settings
        self._prospecting_settings = prospecting_settings
        self._client = openrouter_client
        self._browser_client = browser_client
        self._person_store = person_store
        self._campaign_store = campaign_store

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "prospecting.researching")

        campaign_id = await self._campaign_store.create(ctx.prompt)

        reachable = await self._browser_client.health()
        if not reachable:
            self._log.warning(
                "browser_service_unreachable", campaign_id=str(campaign_id)
            )

        tool_names = (
            self.tools
            if reachable
            else [t for t in self.tools if t != "browser_extract"]
        )

        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        deps = {
            "browser_client": self._browser_client,
            "browser_delay_ms": self._prospecting_settings.browser_delay_ms,
            "browser_max_text_chars": self._prospecting_settings.browser_max_text_chars,
            "person_store": self._person_store,
            "campaign_store": self._campaign_store,
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
                max_iterations=self._prospecting_settings.max_iterations,
                max_history_tokens=self._prospecting_settings.max_loop_tokens,
                max_tokens=4000,
            )

            if tool_calls:
                await self._campaign_store.complete(campaign_id, response)
            else:
                # No research happened — likely a mis-routed or conversational turn.
                # Don't leave an empty campaign behind.
                await self._campaign_store.discard(campaign_id)
                self._log.info(
                    "campaign_discarded_no_work", campaign_id=str(campaign_id)
                )

            return AgentResult(
                agent=self.name,
                response=response,
                tool_calls=tool_calls,
            )
        except Exception:
            await self._campaign_store.fail(campaign_id)
            raise

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        raise NotImplementedError("ProspectingAgent does not support streaming")
        yield  # make mypy happy
