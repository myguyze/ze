from __future__ import annotations

import asyncio
from typing import Any, TYPE_CHECKING

import asyncpg

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_agents.plugin import ZePlugin
from ze_agents.settings import Settings as CoreSettings
from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.push_log_store import PushLogStore
from ze_calendar.reminders.calendar_store import CalendarReminderStore
from ze_calendar.reminders.store import ReminderStore, fire_reminder

if TYPE_CHECKING:
    from ze_google.auth import GoogleCredentials

log = get_logger(__name__)


class CalendarPlugin(ZePlugin):
    """Registers calendar + reminder agents and the calendar reminder job."""

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        openrouter_client: LLMClient,
        settings: CoreSettings,
        google_credentials: "GoogleCredentials | None" = None,
    ) -> None:
        self._pool = pool
        self._notifier = notifier
        self._push_log_store = push_log_store
        self._openrouter_client = openrouter_client
        self._settings = settings
        self._google_credentials = google_credentials

        self.reminder_store = ReminderStore(pool=pool)
        self._calendar_reminder_store = CalendarReminderStore(pool=pool)

    def rest_stores(self) -> dict[str, Any]:
        return {"reminder_store": self.reminder_store}

    def agent_deps(self, accumulated: dict) -> dict:
        return {ReminderStore: self.reminder_store}

    def memory_policies(self) -> dict[str, Any]:
        from ze_memory.policies import CalendarPolicy, RemindersPolicy

        return {
            "calendar": CalendarPolicy(),
            "reminders": RemindersPolicy(),
        }

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_calendar.agents.calendar.agent",
            "ze_calendar.agents.reminders.agent",
        ]

    async def startup(self, container: Any) -> None:
        from ze_calendar.reminders.calendar import CalendarReminderService
        from ze_calendar.jobs.calendar_reminder import CalendarReminderJob

        calendar_reminder_service = CalendarReminderService(
            notifier=self._notifier,
            store=self._calendar_reminder_store,
            push_log_store=self._push_log_store,
            openrouter_client=self._openrouter_client,
            scheduler=container.workflow_scheduler,
            settings=self._settings,
        )

        calendar_reminders = CalendarReminderJob(
            service=calendar_reminder_service,
            credentials=self._google_credentials,
        )

        proactive_cfg = self._settings.config.get("proactive", {})
        calendar_cfg = proactive_cfg.get("calendar", {})
        if calendar_cfg.get("sync_enabled", True):
            await calendar_reminder_service.replay_unsent()
            container.proactive_scheduler.register(
                calendar_reminders,
                cron=calendar_cfg.get("sync_cron", "45 7 * * *"),
            )
            log.info("calendar_reminders_scheduled")

        # Replay unsent user reminders — fire overdue ones now, schedule future ones.
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        unsent = await self.reminder_store.list_all_unsent()
        overdue = 0
        for r in unsent:
            if r.fire_at <= now:
                asyncio.create_task(
                    fire_reminder(self.reminder_store, self._notifier, r.id)
                )
                overdue += 1
            else:
                container.workflow_scheduler.schedule_at(
                    fn=lambda rid=r.id: fire_reminder(
                        self.reminder_store, self._notifier, rid
                    ),
                    dt=r.fire_at,
                    job_id=f"user_reminder:{r.id}",
                )
        if unsent:
            log.info(
                "reminders_replayed",
                total=len(unsent),
                overdue=overdue,
                scheduled=len(unsent) - overdue,
            )
