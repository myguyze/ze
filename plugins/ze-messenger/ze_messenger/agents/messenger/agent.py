from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.client import LLMClient
from ze_agents.registry import agent
from ze_agents.settings import Settings
from ze_agents.types import AgentContext, AgentResult, Intent, Mode
from ze_communication.channel import InboundChannel
from ze_communication.registry import ChannelRegistry
from ze_personal.channels.thread_channel_map import ThreadChannelMap
from ze_personal.channels.user_channel_store import UserChannelStore
from ze_personal.contacts.extractors import extract_email_contacts

_AGENT_INSTRUCTIONS = """\
You manage the user's messaging inbox across communication channels.

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
class MessengerAgent(BaseAgent):
    name = "messenger"
    display_name = "Messenger"
    description = """
      Messaging and inbox management across communication channels.
      Use for: "do I have any emails from X", "check my inbox", "what's in my email",
      "draft a message to X about Y", "send an email to X", "reply to X's email",
      "forward this email", "summarise my email thread", "archive this email",
      "search my inbox for X". Not for calendar events or reminders.
    """
    model = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    tools = ["list_emails", "get_email", "draft_email", "send_email", "archive_email"]
    intents = {
        "read": Intent(Mode.AUTONOMOUS, "Search and retrieve emails from Gmail."),
        "create": Intent(Mode.DRAFT_ONLY, "Draft or send an email."),
        "update": Intent(Mode.DRAFT_ONLY, "Draft a reply or forward."),
        "delete": Intent(Mode.CONFIRM, "Archive or delete an email."),
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        channel_registry: ChannelRegistry,
        user_channel_store: UserChannelStore,
        thread_channel_map: ThreadChannelMap,
        settings: Settings,
    ) -> None:
        self._client = openrouter_client
        self._registry = channel_registry
        self._user_channels = user_channel_store
        self._thread_map = thread_channel_map
        self._settings = settings

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = (
            "email.drafting" if ctx.intent in ("create", "update") else "email.reading"
        )
        await self.emit(ctx, key)

        default_channel = await self._default_channel()

        deps: dict = {
            "channel_registry": self._registry,
            "thread_channel_map": self._thread_map,
            "user_channel_store": self._user_channels,
        }
        if default_channel is not None and hasattr(default_channel, "_creds"):
            deps["credentials"] = default_channel._creds

        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps=deps,
        )

        contact_proposals = extract_email_contacts(loop_tool_calls)

        self._log.info(
            "messenger_agent_complete",
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
        default_channel = await self._default_channel()
        creds = getattr(default_channel, "_creds", None) if default_channel else None
        inbox_tc = None
        if creds is not None:
            inbox_tc = await self.call_tool("list_emails", ctx, credentials=creds)

        augmented = ctx.prompt
        if inbox_tc and inbox_tc.success and inbox_tc.result:
            augmented = f"{ctx.prompt}\n\nRecent emails:\n{inbox_tc.result}"

        async for token in self._client.stream(
            messages=[{"role": "user", "content": augmented}],
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        ):
            yield token

    async def _default_channel(self) -> InboundChannel | None:
        uc = await self._user_channels.get_default_outbound("email")
        if uc:
            return self._registry.get_inbound_by_id(uc.channel_id)
        channels = [
            c
            for c in self._registry.inbound_channels()
            if c.channel_type.value == "email"
        ]
        return channels[0] if channels else None
