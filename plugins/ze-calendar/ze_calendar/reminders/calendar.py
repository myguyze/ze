from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from ze_core.logging import get_logger
from ze_core.proactive.push_log_store import PushLogStore
from ze_calendar.reminders.calendar_store import CalendarReminderStore
from ze_core.openrouter.client import OpenRouterClient
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.telemetry.context import set_agent_context, set_flow_context

log = get_logger(__name__)

_ASSESS_SYSTEM = """\
You are Ze's calendar assistant. Given a calendar event, return a JSON object
with a single key "intervals" — an array of strings representing reminder
offsets before the event start time. Choose intervals that would help a person
prepare appropriately. Use values like "2 weeks", "3 days", "2 hours",
"30 minutes". Return only the JSON object. Do not explain."""

_UNIT_SECONDS: dict[str, int] = {
    "week": 7 * 24 * 3600,
    "day": 24 * 3600,
    "hour": 3600,
    "minute": 60,
    "min": 60,
}

_MIN_OFFSET = timedelta(minutes=5)
_MAX_OFFSET = timedelta(days=14)
_SOON_THRESHOLD = timedelta(minutes=10)


def _parse_interval(s: str) -> timedelta | None:
    parts = s.strip().lower().split()
    if len(parts) != 2:
        return None
    try:
        n = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].rstrip("s")
    seconds_per_unit = _UNIT_SECONDS.get(parts[1]) or _UNIT_SECONDS.get(unit)
    if not seconds_per_unit:
        return None
    td = timedelta(seconds=int(n * seconds_per_unit))
    if td < _MIN_OFFSET or td > _MAX_OFFSET:
        return None
    return td


def _human_offset(td: timedelta) -> str:
    total = int(td.total_seconds())
    days = total // 86400
    hours = (total % 86400) // 3600
    minutes = (total % 3600) // 60
    if days >= 7:
        weeks = days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''}"
    if days > 0:
        return f"{days} day{'s' if days > 1 else ''}"
    if hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''}"
    return f"{minutes} minute{'s' if minutes > 1 else ''}"


def _event_start(event: dict) -> datetime | None:
    start = event.get("start", {})
    if "dateTime" in start:
        return datetime.fromisoformat(start["dateTime"]).astimezone(timezone.utc)
    if "date" in start:
        from datetime import date as _date
        d = _date.fromisoformat(start["date"])
        return datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=timezone.utc)
    return None


def _event_updated(event: dict) -> datetime | None:
    updated = event.get("updated")
    if not updated:
        return None
    return datetime.fromisoformat(updated.replace("Z", "+00:00")).astimezone(timezone.utc)


class CalendarReminderService:
    def __init__(
        self,
        notifier: ProactiveNotifier,
        store: CalendarReminderStore,
        push_log_store: PushLogStore,
        openrouter_client: OpenRouterClient,
        scheduler: Any,  # WorkflowScheduler — avoids circular import
        settings: Any,   # ze_api.settings.Settings — not imported to avoid circular dep
    ) -> None:
        self._notifier = notifier
        self._store = store
        self._push_log = push_log_store
        self._client = openrouter_client
        self._scheduler = scheduler
        self._settings = settings

    async def sync(self, credentials: Any) -> None:
        """Fetch upcoming calendar events and schedule reminders for them."""
        set_flow_context("calendar_sync")
        set_agent_context("reminders")
        if credentials is None:
            log.info("reminder_sync_skipped_no_credentials")
            return

        days_ahead = int(
            self._settings.proactive_config.get("calendar", {}).get("sync_days_ahead", 7)
        )
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=days_ahead)

        try:
            service = credentials.calendar()
            result = await asyncio.to_thread(
                lambda: service.events().list(
                    calendarId="primary",
                    timeMin=now.isoformat(),
                    timeMax=time_max.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                ).execute()
            )
            events = result.get("items", [])
        except Exception as exc:
            log.warning("calendar_sync_failed", error=str(exc))
            return

        log.info("calendar_sync_fetched", count=len(events))
        for event in events:
            await self._process_event(event, now)

    async def replay_unsent(self) -> None:
        """Startup recovery: re-register unsent reminders into the scheduler."""
        reminders = await self._store.list_unsent()
        for r in reminders:
            self._scheduler.schedule_at(
                fn=self.fire_reminder,
                dt=r.fire_at,
                job_id=f"reminder:{r.id}",
                args=(r.id,),
            )
        log.info("reminders_replayed", count=len(reminders))

    async def fire_reminder(self, reminder_id: UUID) -> None:
        """Scheduler callback: push the notification and mark the reminder sent."""
        label = await self._store.mark_sent(reminder_id)
        if label is None:
            return
        await self._notifier.push(label)
        await self._push_log.log(f"calendar_reminder:{reminder_id}", label)
        log.info("reminder_fired", id=str(reminder_id))

    # ── Private ───────────────────────────────────────────────────────────────

    async def _process_event(self, event: dict, now: datetime) -> None:
        event_id = event.get("id", "")
        title = event.get("summary") or "(Untitled event)"
        start_time = _event_start(event)
        if start_time is None or start_time <= now:
            return

        event_updated = _event_updated(event)
        existing = await self._store.list_for_event(event_id)

        if existing:
            latest_assessed = max(r.assessed_at for r in existing)
            if event_updated and event_updated > latest_assessed:
                deleted_ids = await self._store.delete_unsent_for_event(event_id)
                for rid in deleted_ids:
                    self._scheduler.remove_job_if_exists(f"reminder:{rid}")
                await self._schedule_event(event_id, title, start_time, event, now, is_update=True)
            return

        await self._schedule_event(event_id, title, start_time, event, now, is_update=False)

    async def _schedule_event(
        self,
        event_id: str,
        title: str,
        start_time: datetime,
        event: dict,
        now: datetime,
        is_update: bool,
    ) -> None:
        fire_ats = await self._assess_intervals(event, start_time, now)
        if not fire_ats:
            return

        prefix = "📅 Reminders updated" if is_update else "📅 Reminders set"
        confirmation_lines = [f'{prefix} for "{title}"']

        for offset, fire_at in fire_ats:
            label = (
                f"⏰ {title} — starting in {_human_offset(offset)}\n"
                f"{start_time.strftime('%a %d %b %Y at %H:%M UTC')}"
            )
            rid = await self._store.create(event_id, title, fire_at, label)
            self._scheduler.schedule_at(
                fn=self.fire_reminder,
                dt=fire_at,
                job_id=f"reminder:{rid}",
                args=(rid,),
            )
            confirmation_lines.append(
                f"  • {_human_offset(offset)} before — {fire_at.strftime('%a %d %b %H:%M UTC')}"
            )

        confirmation_lines.extend(["", "Tell me if you'd like to change these."])
        await self._notifier.push("\n".join(confirmation_lines))
        log.info("event_reminders_scheduled", event_id=event_id, count=len(fire_ats))

    async def _assess_intervals(
        self,
        event: dict,
        start_time: datetime,
        now: datetime,
    ) -> list[tuple[timedelta, datetime]]:
        model = self._settings.config.get("models", {}).get(
            "reminders", "anthropic/claude-haiku-4-5"
        )
        end_time = _event_start({"start": event.get("end", {})})
        duration_minutes = (
            int((end_time - start_time).total_seconds() / 60)
            if end_time and end_time > start_time
            else 60
        )

        user_prompt = (
            f"Event: {event.get('summary') or 'Untitled'}\n"
            f"Duration: {duration_minutes} minutes\n"
            f"Description: {event.get('description') or '(none)'}"
        )

        raw_intervals: list[str] = ["1 hour"]
        try:
            raw = await self._client.complete(
                messages=[{"role": "user", "content": user_prompt}],
                model=model,
                system=_ASSESS_SYSTEM,
                max_tokens=150,
            )
            parsed = json.loads(raw)
            if isinstance(parsed.get("intervals"), list):
                raw_intervals = [str(x) for x in parsed["intervals"]]
        except Exception as exc:
            log.warning("interval_assessment_failed", error=str(exc))

        result: list[tuple[timedelta, datetime]] = []
        for interval_str in raw_intervals:
            td = _parse_interval(interval_str)
            if td is None:
                continue
            fire_at = start_time - td
            if fire_at <= now + _SOON_THRESHOLD:
                continue
            result.append((td, fire_at))
        return result
