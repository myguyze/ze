from typing import AsyncIterator

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.capability.types import Mode
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_email.channel.gmail import GmailChannel
from ze_personal.contacts.extractors import extract_email_contacts
from ze_google.auth import GoogleCredentials
from ze_core.openrouter.client import OpenRouterClient
from ze_core.settings import Settings

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


@agent
class EmailAgent(BaseAgent):
    name = "email"
    description = """
      Manages Gmail messages. Use for reading, drafting, sending, or archiving emails,
      searching your inbox, or composing replies.
    """
    model = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    tools = ["list_emails", "get_email", "draft_email", "send_email", "archive_email"]
    intent_map = {
        "read": "Search and retrieve emails from Gmail.",
        "create": "Draft or send an email.",
        "update": "Draft a reply or forward.",
        "delete": "Archive or delete an email.",
    }
    capabilities = {
        "read": Mode.AUTONOMOUS,
        "create": Mode.DRAFT_ONLY,
        "update": Mode.DRAFT_ONLY,
        "delete": Mode.CONFIRM,
    }

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        google_credentials: GoogleCredentials,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client
        self._creds = google_credentials
        self._gmail_channel = GmailChannel(credentials=google_credentials)

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = "email.drafting" if ctx.intent in ("create", "update") else "email.reading"
        await self.emit(ctx, key)
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={"credentials": self._creds, "gmail_channel": self._gmail_channel},
        )

        contact_proposals = extract_email_contacts(loop_tool_calls)

        self._log.info(
            "email_agent_complete",
            session_id=ctx.session_id,
            tool_calls=len(loop_tool_calls),
            contact_proposals=len(contact_proposals),
        )

        return AgentResult(
            agent=self.name,
            response=response,
            tool_calls=loop_tool_calls,
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
