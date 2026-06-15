import re
from typing import AsyncIterator

import asyncpg

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import AgentContext, AgentResult, ToolCall
from ze_personal.contacts.store import PersonStore
from ze_agents.client import LLMClient
from ze_agents.settings import Settings
from ze_agents.types import Mode

_AGENT_INSTRUCTIONS = """\
You reason from what you know and what the user tells you — you do not search the web.
Never label your role or use phrases like "as your companion", "as your assistant", \
or "I'm here to". Just respond naturally.

- Reflect, explore ideas, and help the user think through problems.
- Be honest when you don't know something or when a question requires current data you lack.
- Match the user's energy: casual for casual topics, substantive when they need depth.\
"""

_EVENT_KEYWORDS: dict[str, list[str]] = {
    "no_reply": ["no reply", "no response", "hasn't replied", "hasn't responded"],
    "bounced": ["bounced", "returned", "undeliverable"],
    "replied": ["replied", "responded", "got back", "wrote back"],
    "sent": ["sent", "emailed", "messaged", "reached out to", "contacted"],
}

_CHANNEL_KEYWORDS: dict[str, list[str]] = {
    "email": ["email", "emailed"],
    "linkedin": ["linkedin"],
    "sms": ["sms", "text", "texted", "whatsapp"],
    "phone": ["call", "called", "phone", "rang"],
}


@agent
class CompanionAgent(BaseAgent):
    name = "companion"
    display_name = "Conversation & reasoning"
    description = """
      Chat, conversation, and reasoning that needs no external tools or live data.
      Use for: greetings ("hey", "how are you doing"), emotional check-ins ("I'm feeling
      stressed"), brainstorming, writing help, "explain X to me", "help me think through X",
      "what can you do", "what do you know about me", "tell me something interesting",
      and open-ended questions with no specific domain. Not for web search, calendar,
      email, reminders, news, or any query that needs fetching live data.
    """
    model = "anthropic/claude-sonnet-4-5"
    model_simple = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 60
    tools = []
    intent_map = {"reason": "direct_completion"}
    capabilities = {
        "reason": Mode.AUTONOMOUS,
        "read": Mode.AUTONOMOUS,
        "create": Mode.AUTONOMOUS,
        "update": Mode.AUTONOMOUS,
        "delete": Mode.AUTONOMOUS,
        "execute": Mode.AUTONOMOUS,
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        settings: Settings,
        person_store: PersonStore,
        pool: asyncpg.Pool,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client
        self._person_store = person_store
        self._pool = pool

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "companion.thinking")
        response = await self._client.complete(
            messages=ctx.messages,
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        )

        tool_calls = []
        outreach_tc = await self._attempt_log_outreach(ctx)
        if outreach_tc is not None and outreach_tc.success:
            tool_calls.append(outreach_tc)

        self._log.info("companion_agent_complete", session_id=ctx.session_id)
        return AgentResult(agent=self.name, response=response, tool_calls=tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        async for token in self._client.stream(
            messages=ctx.messages,
            model=self._model(ctx),
            system=self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx),
        ):
            yield token

    async def _attempt_log_outreach(self, ctx: AgentContext) -> ToolCall | None:
        event = _detect_outreach_event(ctx.prompt)
        if event is None:
            return None
        return await self.call_tool(
            "log_outreach_event", ctx,
            contact_name=event["contact_name"],
            event_type=event["event_type"],
            channel=event["channel"],
            notes=ctx.prompt,
            pool=self._pool,
            person_store=self._person_store,
        )


def _detect_outreach_event(text: str) -> dict | None:
    lower = text.lower()

    event_type = None
    for et, keywords in _EVENT_KEYWORDS.items():
        if any(k in lower for k in keywords):
            event_type = et
            break

    if event_type is None:
        return None

    names = re.findall(
        r"\b[A-Z][a-záàâãéèêíïóôõöúüçñ]+(?:\s+[A-Z][a-záàâãéèêíïóôõöúüçñ]+)?\b",
        text,
    )
    if not names:
        return None

    channel = "other"
    for ch, keywords in _CHANNEL_KEYWORDS.items():
        if any(k in lower for k in keywords):
            channel = ch
            break

    return {"contact_name": names[0], "event_type": event_type, "channel": channel}
