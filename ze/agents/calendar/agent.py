from typing import AsyncIterator

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.google.auth import GoogleCredentials
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.tools.facts import to_user_facts

_AGENT_INSTRUCTIONS = """\
You manage the user's Google Calendar. All times are in {timezone}.

- Before creating or modifying events, confirm the details.
- When listing events, summarize concisely: title, date/time, location if present.
- Resolve ambiguous time references ("tomorrow", "next week") explicitly before acting.
- If an operation fails, explain what went wrong clearly.\
"""


@register
class CalendarAgent(BaseAgent):
    name  = "calendar"
    tools = ["list_events", "create_event", "update_event", "delete_event", "extract_facts"]

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        google_credentials: GoogleCredentials,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._creds  = google_credentials

    async def run(self, ctx: AgentContext) -> AgentResult:
        events_tc = await self.call_tool(
            "list_events", ctx, credentials=self._creds
        )

        augmented = ctx.prompt
        if events_tc.success and events_tc.result:
            augmented = f"{ctx.prompt}\n\nUpcoming events:\n{events_tc.result}"

        response = await self._client.complete(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx, timezone=self._settings.timezone),
        )

        facts_tc = await self.call_tool(
            "extract_facts", ctx,
            prompt=ctx.prompt,
            response=response,
            client=self._client,
            model=self._model(ctx),
        )

        proposals = to_user_facts(facts_tc.result or [])

        self._log.info(
            "calendar_agent_complete",
            session_id=ctx.session_id,
            events_fetched=len(events_tc.result or []),
            proposals=len(proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=[events_tc, facts_tc],
            memory_proposals=proposals,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        events_tc = await self.call_tool(
            "list_events", ctx, credentials=self._creds
        )
        augmented = ctx.prompt
        if events_tc.success and events_tc.result:
            augmented = f"{ctx.prompt}\n\nUpcoming events:\n{events_tc.result}"

        async for token in self._client.stream(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx, timezone=self._settings.timezone),
        ):
            yield token
