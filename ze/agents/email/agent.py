from typing import AsyncIterator

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.channels.email import EmailChannel
from ze.contacts.extractors import extract_email_contacts
from ze.google.auth import GoogleCredentials
from ze.openrouter.client import OpenRouterClient
from ze.settings import Settings
from ze.tools.facts import to_user_facts

_AGENT_INSTRUCTIONS = """\
You manage the user's Gmail inbox.

Available tools:
- list_emails: search messages using Gmail query syntax (from:, subject:, is:unread, etc.)
- get_email: retrieve the full content of a message by message_id
- draft_email: create a draft without sending
- send_email: send an email immediately
- archive_email: remove a message from the inbox by message_id

Guidelines:
- Emails are plain text only — no HTML in the body.
- Use list_emails then get_email to read content before drafting replies.
- Summarize email content concisely: sender, subject, key points.
- Use send_email with thread_id to reply within an existing thread.
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
        self._client        = openrouter_client
        self._creds         = google_credentials
        self._email_channel = EmailChannel(credentials=google_credentials)

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = "email.drafting" if ctx.intent in ("create", "update") else "email.reading"
        await self.emit(ctx, key)
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={"credentials": self._creds, "email_channel": self._email_channel},
            tool_names=["list_emails", "get_email", "draft_email", "send_email", "archive_email"],
        )

        facts_tc = await self.call_tool(
            "extract_facts", ctx,
            prompt=ctx.prompt,
            response=response,
            client=self._client,
            model=self._model(ctx),
        )

        proposals = to_user_facts(facts_tc.result or [])
        contact_proposals = extract_email_contacts(loop_tool_calls)

        self._log.info(
            "email_agent_complete",
            session_id=ctx.session_id,
            tool_calls=len(loop_tool_calls),
            proposals=len(proposals),
            contact_proposals=len(contact_proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=loop_tool_calls + [facts_tc],
            memory_proposals=proposals,
            contact_proposals=contact_proposals,
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
