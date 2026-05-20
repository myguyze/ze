from typing import AsyncIterator

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.google.auth import GoogleCredentials
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.tools.facts import to_user_facts

_AGENT_INSTRUCTIONS = """\
You manage the user's Gmail inbox.

- Emails are plain text only — no HTML or markdown in the body.
- Before sending, always ask for confirmation.
- Summarize email content concisely: sender, subject, key points.
- When searching, use Gmail query syntax (from:, subject:, is:unread, etc.).
- If an operation fails, explain what went wrong clearly.\
"""


@register
class EmailAgent(BaseAgent):
    name  = "email"
    tools = ["list_emails", "get_email", "draft_email", "send_email", "archive_email", "extract_facts"]

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
        inbox_tc = await self.call_tool(
            "list_emails", ctx, credentials=self._creds
        )

        augmented = ctx.prompt
        if inbox_tc.success and inbox_tc.result:
            augmented = f"{ctx.prompt}\n\nRecent emails:\n{inbox_tc.result}"

        response = await self._client.complete(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
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
            "email_agent_complete",
            session_id=ctx.session_id,
            emails_fetched=len(inbox_tc.result or []),
            proposals=len(proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=[inbox_tc, facts_tc],
            memory_proposals=proposals,
        )

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        inbox_tc = await self.call_tool(
            "list_emails", ctx, credentials=self._creds
        )
        augmented = ctx.prompt
        if inbox_tc.success and inbox_tc.result:
            augmented = f"{ctx.prompt}\n\nRecent emails:\n{inbox_tc.result}"

        async for token in self._client.stream(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        ):
            yield token
