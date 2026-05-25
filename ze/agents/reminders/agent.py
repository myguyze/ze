from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ze.agents.base import BaseAgent
from ze.agents.registry import register
from ze.agents.types import AgentContext, AgentResult
from ze.openrouter.client import OpenRouterClient
from ze.proactive.notifier import ProactiveNotifier
from ze.reminders.store import ReminderStore, fire_reminder
from ze.routing.haiku_fallback import _extract_json_object
from ze.settings import Settings
from ze.workflow.scheduler import WorkflowScheduler

_PARSE_SYSTEM = """\
You extract reminder details from user requests.

Current UTC time: {now}
User timezone: {timezone}

Return a JSON object with these fields:
- "action": one of "set", "list", or "cancel"
- "label": concise imperative phrase for what to be reminded about (e.g. "Call João"). Use "Reminder" if unspecified.
- "fire_at": ISO 8601 UTC datetime string for "set" actions; null for "list" or "cancel"
- "cancel_hint": keywords from the reminder label to cancel; null for "set" or "list"

For relative times ("in 2 hours", "tomorrow at 9am"), compute the absolute UTC datetime
using the current time and user timezone above.
Return ONLY the JSON — no explanation, no markdown.\
"""


@register
class RemindersAgent(BaseAgent):
    name = "reminders"
    tools: list[str] = []

    def __init__(
        self,
        openrouter_client: OpenRouterClient,
        reminder_store: ReminderStore,
        workflow_scheduler: WorkflowScheduler,
        notifier: ProactiveNotifier,
        settings: Settings,
    ) -> None:
        super().__init__(settings)
        self._client = openrouter_client
        self._store = reminder_store
        self._scheduler = workflow_scheduler
        self._notifier = notifier

    async def run(self, ctx: AgentContext) -> AgentResult:
        await self.emit(ctx, "reminders.thinking")

        now = datetime.now(timezone.utc)
        raw = await self._client.complete(
            messages=[{"role": "user", "content": ctx.prompt}],
            model=self._model(ctx),
            system=_PARSE_SYSTEM.format(
                now=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                timezone=self._settings.timezone,
            ),
            max_tokens=200,
            response_format={"type": "json_object"},
        )

        try:
            parsed = json.loads(_extract_json_object(raw))
        except json.JSONDecodeError:
            return AgentResult(
                agent=self.name,
                response="I couldn't understand that reminder request. Try: 'remind me in 2 hours to call João'.",
            )

        action = parsed.get("action", "set")
        match action:
            case "set":
                response = await self._handle_set(parsed, now)
            case "list":
                response = await self._handle_list()
            case "cancel":
                response = await self._handle_cancel(parsed)
            case _:
                response = "Unknown reminder action."

        self._log.info("reminders_agent_complete", session_id=ctx.session_id, action=action)
        return AgentResult(agent=self.name, response=response)

    async def stream(self, ctx: AgentContext) -> AsyncIterator[str]:
        result = await self.run(ctx)
        yield result.response

    # ── Handlers ─────────────────────────────────────────────────────────────

    async def _handle_set(self, parsed: dict, now: datetime) -> str:
        label = (parsed.get("label") or "Reminder").strip()
        fire_at_str = parsed.get("fire_at")

        if not fire_at_str:
            return "I need a time to set the reminder. Try: 'remind me in 2 hours'."

        try:
            dt = datetime.fromisoformat(fire_at_str)
            fire_at = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            return "I couldn't parse that time. Try something like 'remind me in 2 hours'."

        if fire_at <= now:
            return "That time is already in the past. Please give me a future time."

        rid = await self._store.create(label=label, fire_at=fire_at)
        self._scheduler.schedule_at(
            fn=fire_reminder,
            dt=fire_at,
            job_id=f"user_reminder:{rid}",
            args=(self._store, self._notifier, rid),
        )

        human = _human_delta(fire_at - now)
        time_str = _format_local(fire_at, self._settings.timezone)
        return f"⏰ Reminder set: {label}\nI'll remind you {human} ({time_str})"

    async def _handle_list(self) -> str:
        pending = await self._store.list_pending()
        if not pending:
            return "You have no pending reminders."
        tz = self._settings.timezone
        lines = [f"⏰ Pending reminders ({len(pending)}):"]
        for i, r in enumerate(pending, 1):
            lines.append(f"  {i}. {r.label} — {_format_local(r.fire_at, tz)}")
        return "\n".join(lines)

    async def _handle_cancel(self, parsed: dict) -> str:
        hint = (parsed.get("cancel_hint") or "").strip().lower()
        pending = await self._store.list_pending()

        if not pending:
            return "You have no pending reminders to cancel."

        matches = [r for r in pending if hint and hint in r.label.lower()]
        if not matches:
            lines = ["I couldn't find a reminder matching that. Your pending reminders:\n"]
            for i, r in enumerate(pending, 1):
                lines.append(f"  {i}. {r.label} — {r.fire_at.strftime('%a %d %b at %H:%M UTC')}")
            lines.append("\nTell me which one you'd like to cancel.")
            return "\n".join(lines)

        target = matches[0]
        self._scheduler.remove_job_if_exists(f"user_reminder:{target.id}")
        await self._store.delete(target.id)
        return f"✅ Reminder cancelled: {target.label}"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_local(dt: datetime, tz_name: str) -> str:
    """Format a UTC datetime in the user's local timezone."""
    try:
        local = dt.astimezone(ZoneInfo(tz_name))
        abbr = local.strftime("%Z")
        return local.strftime(f"%a %d %b at %H:%M {abbr}")
    except ZoneInfoNotFoundError:
        return dt.strftime("%a %d %b at %H:%M UTC")


def _human_delta(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60

    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes and not days:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    if not parts:
        parts = ["less than a minute"]
    return "in " + " ".join(parts)
