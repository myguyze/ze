from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, TYPE_CHECKING

import asyncpg

from ze_agents.client import LLMClient
from ze_agents.logging import get_logger
from ze_sdk import ZePlugin
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

    @classmethod
    def integration_types(cls) -> list[type]:
        from ze_google.auth import GoogleCredentials
        return [GoogleCredentials]

    def data_domains(self):
        from ze_sdk import DataDomain
        from ze_api.data.assembler import bulk_insert

        async def _export(tbl: str, pool) -> list[dict]:
            async with pool.acquire() as conn:
                rows = await conn.fetch(f"SELECT * FROM {tbl}")
                return [dict(r) for r in rows]

        async def _delete(tbl: str, pool) -> None:
            async with pool.acquire() as conn:
                await conn.execute(f"DELETE FROM {tbl}")

        def _domain(name: str, tbl: str) -> DataDomain:
            return DataDomain(
                name,
                lambda p, t=tbl: _export(t, p),
                lambda p, t=tbl: _delete(t, p),
                delete_order=10,
                importer=lambda conn, rows, t=tbl: bulk_insert(conn, t, rows),
            )

        return [
            _domain("calendar.reminders", "user_reminders"),
            _domain("calendar.calendar_reminders", "calendar_reminders"),
        ]

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

    def signal_sources(self) -> list:
        from ze_calendar.signals import CalendarSignalSource

        return [CalendarSignalSource(store=self._calendar_reminder_store)]

    @classmethod
    def migrations_path(cls) -> Path | None:
        return Path(__file__).parent / "migrations"

    def agent_module_paths(self) -> list[str]:
        return [
            "ze_calendar.agents.calendar.agent",
            "ze_calendar.agents.reminders.agent",
        ]

    async def startup(self, container: Any) -> None:
        from ze_calendar.reminders.calendar import CalendarReminderService
        from ze_calendar.jobs.calendar_reminder import CalendarReminderJob
        from ze_calendar.signals import CalendarSignalSource

        calendar_reminder_service = CalendarReminderService(
            notifier=self._notifier,
            store=self._calendar_reminder_store,
            push_log_store=self._push_log_store,
            openrouter_client=self._openrouter_client,
            scheduler=container.workflow_scheduler,
            settings=self._settings,
        )

        signal_source = CalendarSignalSource(store=self._calendar_reminder_store)
        admission_gate = self._build_admission_gate(container)

        calendar_reminders = CalendarReminderJob(
            service=calendar_reminder_service,
            credentials=self._google_credentials,
            signal_source=signal_source if admission_gate is not None else None,
            admission_gate=admission_gate,
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

    def _build_admission_gate(self, container: Any) -> Any:
        salience_cfg = self._settings.config.get("correlation", {}).get("salience", {})
        if not salience_cfg:
            return None

        memory_store = getattr(container, "memory_store", None)
        if memory_store is None:
            return None

        from ze_memory.admission import AdmissionGate
        from ze_memory.relevance import RelevanceModel

        rel_cfg = salience_cfg.get("relevance", {})
        relevance_model = RelevanceModel(
            memory_store=memory_store,
            episode_lookback_days=int(rel_cfg.get("episode_lookback_days", 30)),
            cache_ttl_minutes=int(rel_cfg.get("cache_ttl_minutes", 30)),
        )
        adm_cfg = salience_cfg.get("admission", {})
        return AdmissionGate(
            relevance_model=relevance_model,
            memory_store=memory_store,
            tau_admit=float(adm_cfg.get("tau_admit", 0.55)),
            tau_watch=float(adm_cfg.get("tau_watch", 0.35)),
            w_relevance=float(adm_cfg.get("w_relevance", 0.7)),
            w_magnitude=float(adm_cfg.get("w_magnitude", 0.3)),
            watch_buffer_ttl_hours=float(adm_cfg.get("watch_buffer_ttl_hours", 48)),
            dry_run=bool(salience_cfg.get("dry_run", False)),
        )
