from typing import AsyncIterator

from ze_agents.base_agent import BaseAgent
from ze_agents.registry import agent
from ze_agents.types import Intent, Mode
from ze_agents.types import AgentContext, AgentResult
from ze_personal.contacts.extractors import extract_calendar_contacts
from ze_google.auth import GoogleCredentials
from ze_agents.client import LLMClient
from ze_agents.settings import Settings
from ze_calendar.timezone.service import TimezoneService

_AGENT_INSTRUCTIONS = """\
You manage the user's Google Calendar. All times are in {timezone}.

Available tools:
- list_events: retrieve upcoming events, optionally filtered by a search query
- create_event: add a new event (summary, ISO-8601 start/end required)
- update_event: modify an existing event by event_id (list first to find the ID)
- delete_event: remove an event by event_id (list first to confirm)
- world_time: get the current local time in one or more cities or IANA timezone names

Guidelines:
- Use ISO-8601 format for all datetimes, including the timezone offset (e.g. 2025-05-23T15:00:00+01:00).
- Resolve ambiguous time references ("tomorrow", "next week") explicitly before acting.
- When listing, summarize concisely: title, date/time, location if present.
- If an operation fails, explain what went wrong clearly.\
"""


@agent
class CalendarAgent(BaseAgent):
    name = "calendar"
    display_name = "Calendar"
    description = """
      Google Calendar events, meetings, and appointments.
      Use for: "what's on my calendar today", "what do I have tomorrow", "what's this week",
      "add a meeting with X on Friday at 3pm", "schedule a call", "create an event",
      "find a free time slot", "am I free on Thursday", "delete my dentist appointment",
      "update my 2pm meeting". Not for one-off personal reminders or email.
    """
    model = "anthropic/claude-haiku-4-5"
    vision_capable = True
    timeout = 30
    tools = ["list_events", "create_event", "update_event", "delete_event", "world_time"]
    intents = {
        "read":   Intent(Mode.AUTONOMOUS, "Search and retrieve calendar events."),
        "create": Intent(Mode.CONFIRM,    "Create a new calendar event."),
        "update": Intent(Mode.CONFIRM,    "Update an existing calendar event."),
        "delete": Intent(Mode.CONFIRM,    "Delete a calendar event."),
    }

    def __init__(
        self,
        openrouter_client: LLMClient,
        google_credentials: GoogleCredentials,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client
        self._creds  = google_credentials
        self._timezone_service = TimezoneService()

    async def run(self, ctx: AgentContext) -> AgentResult:
        key = "calendar.writing" if ctx.intent in ("create", "update", "delete") else "calendar.reading"
        await self.emit(ctx, key)
        system = self._build_system_prompt(_AGENT_INSTRUCTIONS, ctx, timezone=self._settings.timezone)
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={"credentials": self._creds, "timezone_service": self._timezone_service},
        )

        contact_proposals = extract_calendar_contacts(loop_tool_calls)

        self._log.info(
            "calendar_agent_complete",
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
