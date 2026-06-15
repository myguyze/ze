from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import Mode
from ze_agents.types import AgentContext, AgentResult
from ze_email.channel.gmail import GmailChannel
from ze_personal.contacts.extractors import extract_email_contacts
from ze_google.auth import GoogleCredentials
from ze_agents.client import LLMClient
from ze_agents.settings import Settings

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
    display_name = "Email"
    description = """
      Gmail inbox and email management.
      Use for: "do I have any emails from X", "check my inbox", "what's in my email",
      "draft an email to X about Y", "send an email to X", "reply to X's email",
      "forward this email", "summarise my email thread", "archive this email",
      "search my inbox for X". Not for calendar events, reminders, or chat.
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
        openrouter_client: LLMClient,
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
