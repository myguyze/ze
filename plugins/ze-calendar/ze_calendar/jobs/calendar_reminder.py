from typing import Any

from ze_core.proactive.job import proactive_job
from ze_calendar.reminders.calendar import CalendarReminderService


@proactive_job
class CalendarReminderJob:
    job_id = "calendar_reminder_sync"

    def __init__(self, service: CalendarReminderService, credentials: Any) -> None:
        self._service = service
        self._credentials = credentials

    async def run(self) -> None:
        await self._service.sync(self._credentials)
