from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ze_core.interface.types import Notification
from ze_core.logging import get_logger
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_core.proactive.push_log_store import PushLogStore
from ze_personal.goals.planner import GoalPlanner
from ze_personal.goals.store import GoalStore
from ze_personal.goals.types import GoalStatus, MilestoneStatus

log = get_logger(__name__)

_DEDUP_HOURS = 144  # 6 days — prevents double-send on scheduler jitter


@proactive_job
class GoalNarrativeJob:
    job_id = "goal_narrative"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        push_log_store: PushLogStore,
        goal_store: GoalStore,
        goal_planner: GoalPlanner,
    ) -> None:
        self._notifier = notifier
        self._push_log = push_log_store
        self._store = goal_store
        self._planner = goal_planner

    async def run(self) -> None:
        if await self._push_log.was_sent_within_hours("goal_narrative", _DEDUP_HOURS):
            log.info("goal_narrative_skipped_dedup")
            return

        active_goals = await self._store.list_active()
        if not active_goals:
            log.info("goal_narrative_skipped_no_goals")
            return

        since = datetime.now(timezone.utc) - timedelta(days=7)
        paragraphs: list[str] = []

        for goal in active_goals:
            try:
                milestones = await self._store.list_milestones(goal.id)
                completed_this_week = [
                    m for m in milestones
                    if m.status == MilestoneStatus.COMPLETED
                    and m.completed_at is not None
                    and m.completed_at >= since
                ]
                pending_gate = (
                    await self._store.get_pending_gate(goal.id)
                    if goal.status == GoalStatus.AWAITING_GATE
                    else None
                )
                next_milestones = [m for m in milestones if m.status == MilestoneStatus.PENDING]

                if not completed_this_week and pending_gate is None:
                    continue

                paragraph = await self._planner.synthesize_weekly_narrative(
                    goal, completed_this_week, pending_gate, next_milestones
                )
                header = f"<b>{goal.title}</b>"
                if pending_gate is not None:
                    header += f" ⚠️ awaiting gate: {pending_gate.title}"
                paragraphs.append(f"{header}\n{paragraph}")
            except Exception as exc:
                log.warning("goal_narrative_goal_failed", goal_id=str(goal.id), error=str(exc))

        if not paragraphs:
            log.info("goal_narrative_nothing_to_report")
            return

        body = "\n\n".join(paragraphs)
        content = f"<b>Goal progress — this week</b>\n\n{body}"
        await self._notifier.push_notification(
            Notification(content=content, format="html", urgency="normal")
        )
        await self._push_log.log("goal_narrative", "weekly")
        log.info("goal_narrative_sent", goals=len(paragraphs))
