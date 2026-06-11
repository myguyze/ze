from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

from ze_core.orchestration.base_agent import BaseAgent
from ze_core.orchestration.registry import agent
from ze_core.capability.types import Mode
from ze_core.orchestration.types import AgentContext, AgentResult
from ze_core.openrouter.client import OpenRouterClient
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.settings import Settings
from ze_calendar.reminders.store import ReminderStore
from ze_personal.workflow.scheduler import WorkflowScheduler

_AGENT_INSTRUCTIONS = """\
You manage the user's one-off reminders. Current UTC time: {now}. User timezone: {timezone}.

Available tools:
- set_reminder: create a new reminder with a label and a future fire time (ISO-8601 UTC)
- list_reminders: list all pending reminders (returns id, label, fire_at)
- cancel_reminder: cancel a reminder by its ID — call list_reminders first to find the ID

Guidelines:
- Convert relative times ("in 2 hours", "tomorrow at 9am") to absolute UTC ISO-8601 before
  calling set_reminder.
- Format times in the user's local timezone ({timezone}) when confirming or listing.
- When cancelling, always call list_reminders first so you can pass the correct ID.
- Do NOT use this agent for recurring tasks — those belong to the workflow agent.\
"""


@agent
class RemindersAgent(BaseAgent):
    name = "reminders"
    description = """
      Sets, lists, and cancels one-off time-based reminders. Use when the user asks
      to be reminded about something at a specific future time or after a delay,
      or wants to see, check, or cancel their reminders.
      Do NOT use for recurring tasks — use the workflow agent for those.
    """
    model = "anthropic/claude-haiku-4-5"
    vision_capable = False
    timeout = 15
    tools = ["set_reminder", "list_reminders", "cancel_reminder"]
    intent_map = {"manage": "Set, list, or cancel a one-off reminder."}
    capabilities = {
        "manage": Mode.AUTONOMOUS,
        "create": Mode.AUTONOMOUS,
        "read": Mode.AUTONOMOUS,
        "update": Mode.AUTONOMOUS,
        "delete": Mode.AUTONOMOUS,
        "execute": Mode.AUTONOMOUS,
        "reason": Mode.AUTONOMOUS,
    }

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        reminder_store: ReminderStore,
        workflow_scheduler: WorkflowScheduler,
        notifier: ProactiveNotifier,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._client = openrouter_client
        self._store = reminder_store
        self._scheduler = workflow_scheduler
        self._notifier = notifier

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "reminders.thinking")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        system = self._build_system_prompt(
            _AGENT_INSTRUCTIONS, ctx, now=now, timezone=self._settings.timezone
        )
        response, loop_tool_calls = await self.agentic_loop(
            ctx,
            client=self._client,
            messages=list(ctx.messages),
            system=system,
            deps={
                "store": self._store,
                "scheduler": self._scheduler,
                "notifier": self._notifier,
            },
        )
        self._log.info(
            "reminders_agent_complete",
            session_id=ctx.session_id,
            tool_calls=len(loop_tool_calls),
        )
        return AgentResult(agent=self.name, response=response, tool_calls=loop_tool_calls)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response
