from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from ze_logging import get_logger
from ze_sdk.proactive import proactive_job
from ze_calendar.reminders.calendar import CalendarReminderService

if TYPE_CHECKING:
    from ze_calendar.signals import CalendarSignalSource

log = get_logger(__name__)

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@proactive_job
class CalendarReminderJob:
    job_id = "calendar_reminder_sync"

    def __init__(
        self,
        service: CalendarReminderService,
        credentials: Any,
        signal_source: "CalendarSignalSource | None" = None,
        admission_gate: Any = None,
        loop_extractor: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._service = service
        self._credentials = credentials
        self._signal_source = signal_source
        self._admission_gate = admission_gate
        self._signal_watermark: datetime = _EPOCH
        # Optional hook wired post-construction by ze-api (open-loop extraction,
        # FR-008's calendar inflow) — kept generic here so ze-calendar has no
        # dependency on ze-worldstate (plan.md: ze-api is the only wiring point).
        self.loop_extractor = loop_extractor

    async def run(self) -> None:
        await self._service.sync(self._credentials)
        if self._signal_source is not None and self._admission_gate is not None:
            await self._emit_via_source()

    async def _emit_via_source(self) -> None:
        since = self._signal_watermark
        self._signal_watermark = datetime.now(timezone.utc)
        signals = await self._signal_source.poll(since)
        for signal in signals:
            try:
                await self._admission_gate.check_and_ingest(signal)
            except Exception as exc:
                log.warning(
                    "calendar_signal_emit_failed",
                    event_id=signal.external_ref,
                    error=str(exc),
                )
            if self.loop_extractor is not None:
                try:
                    await self.loop_extractor(
                        f"{signal.title}. {signal.summary}", "calendar"
                    )
                except Exception as exc:
                    log.warning(
                        "calendar_loop_extraction_failed",
                        event_id=signal.external_ref,
                        error=str(exc),
                    )
