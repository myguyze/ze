from ze_core.contacts.store import PersonStore
from ze.logging import get_logger
from ze_core.proactive.push_log_store import PushLogStore
from ze.settings import Settings
from ze_core.workflow.store import WorkflowStore
from ze_core.memory.postgres import PostgresMemoryStore
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.telemetry.context import set_flow_context


@proactive_job
class MorningBriefing:
    job_id = "morning_briefing"
    def __init__(
        self,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        memory_store: PostgresMemoryStore,
        workflow_store: WorkflowStore,
        person_store: PersonStore,
        settings: Settings,
    ) -> None:
        self._notifier = notifier
        self._push_log = push_log_store
        self._memory = memory_store
        self._workflows = workflow_store
        self._persons = person_store
        self._settings = settings
        self._log = get_logger(__name__)
        follow_up_cfg = settings.contacts_config.get("follow_up", {})
        self._stale_days = int(follow_up_cfg.get("stale_days", 7))
        self._max_nudges = int(follow_up_cfg.get("max_nudges", 3))

    async def run(self) -> None:
        set_flow_context("morning_briefing")

        if await self._push_log.was_sent_within_hours("morning_brief", 20):
            self._log.info("briefing_skipped_dedup")
            return

        unreviewed = await self._memory.count_unreviewed_facts()
        workflows = await self._workflows.list_enabled_scheduled()
        failures = await self._push_log.list_workflow_failures_within_hours(24)
        stale_contacts = await self._persons.list_stale_for_follow_up(
            self._stale_days, self._max_nudges
        )

        threshold = int(
            self._settings.proactive_config.get("briefing", {}).get("unreviewed_nudge_threshold", 5)
        )

        lines = ["Good morning! Here's your Ze briefing.", ""]
        lines.append(f"📋 Unreviewed facts: {unreviewed}")

        if workflows:
            names = ", ".join(w.name for w in workflows)
            lines.append(f"⚙️  Scheduled workflows: {names}")
        else:
            lines.append("⚙️  Scheduled workflows: none")

        if failures:
            lines.append("")
            for entry in failures:
                name = entry.payload or "unknown"
                when = entry.sent_at.strftime("%H:%M UTC")
                lines.append(f"⚠️  Recent failure: {name} at {when}")

        if unreviewed >= threshold:
            lines.append("")
            lines.append(f"💡 You have {unreviewed} facts waiting for review.")

        if stale_contacts:
            lines.append("")
            lines.append("📌 Follow-up nudges:")
            for nudge in stale_contacts:
                days = nudge.days_ago
                lines.append(
                    f"  • {nudge.name} — last mentioned {days} day{'s' if days != 1 else ''} ago"
                )

        await self._notifier.push("\n".join(lines))
        self._log.info("briefing_sent", unreviewed=unreviewed)
        await self._push_log.log("morning_brief")
