from __future__ import annotations

import html as _html

from ze_core.interface.types import Action, Notification
from ze_core.logging import get_logger
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_personal.goals.store import GoalStore
from ze_personal.goals.types import StuckGoal

log = get_logger(__name__)


@proactive_job
class StuckGoalJob:
    job_id = "stuck_goals"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        goal_store: GoalStore,
    ) -> None:
        self._notifier = notifier
        self._goal_store = goal_store

    async def run(self) -> None:
        stuck = await self._goal_store.list_stuck(
            idle_days=7,
            alert_cooldown_days=14,
        )
        if not stuck:
            log.info("stuck_goals_none")
            return

        log.info("stuck_goals_found", count=len(stuck))

        content, actions = _build_message(stuck)
        await self._notifier.push_notification(Notification(
            content=content,
            format="html",
            urgency="normal",
            actions=actions,
        ))

        for sg in stuck:
            await self._goal_store.mark_stuck_alerted(sg.goal.id)


def _build_message(stuck: list[StuckGoal]) -> tuple[str, list[Action]]:
    count = len(stuck)
    header = (
        "One of your goals needs attention:"
        if count == 1
        else f"{count} of your goals need attention:"
    )

    sections: list[str] = [header]
    actions: list[Action] = []

    for i, sg in enumerate(stuck, start=1):
        goal_id_hex = sg.goal.id.hex
        num = f" #{i}" if count > 1 else ""

        if sg.kind == "awaiting_gate":
            body = (
                f"\n<b>{_html.escape(sg.goal.title)}</b>"
                f" — awaiting your approval for {sg.idle_days} days\n"
                f"Gate: <i>{_html.escape(sg.gate.title)}</i>"
            )
            row = i - 1
            actions += [
                Action(label=f"Approve{num}", payload=f"goal_stuck:gate_approve:{goal_id_hex}", row=row),
                Action(label=f"Redirect{num}", payload=f"goal_stuck:redirect:{goal_id_hex}", row=row),
                Action(label=f"Stop{num}", payload=f"goal_stuck:gate_stop:{goal_id_hex}", row=row),
            ]
        else:
            last = (
                f"Last step: <i>{_html.escape(sg.last_milestone_title)}</i>"
                if sg.last_milestone_title
                else "No steps completed yet."
            )
            body = (
                f"\n<b>{_html.escape(sg.goal.title)}</b>"
                f" — no progress for {sg.idle_days} days\n"
                f"{last}"
            )
            row = i - 1
            actions += [
                Action(label=f"Redirect{num}", payload=f"goal_stuck:redirect:{goal_id_hex}", row=row),
                Action(label=f"Pause{num}", payload=f"goal_stuck:pause:{goal_id_hex}", row=row),
                Action(label=f"Abandon{num}", payload=f"goal_stuck:abandon:{goal_id_hex}", row=row),
            ]

        sections.append(body)

    return "\n".join(sections), actions
