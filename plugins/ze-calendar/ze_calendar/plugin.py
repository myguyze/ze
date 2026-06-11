from ze_core.plugin import ZePlugin


class CalendarPlugin(ZePlugin):
    """Registers calendar + reminder agents and the calendar reminder job."""

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_calendar.agents.calendar.agent",
            "ze_calendar.agents.reminders.agent",
        ]
