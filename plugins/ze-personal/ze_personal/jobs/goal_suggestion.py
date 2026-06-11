from __future__ import annotations

from datetime import datetime, timezone

from ze_core.interface.types import Action, Notification
from ze_core.logging import get_logger
from ze_memory.store import MemoryStore
from ze_core.proactive.job import proactive_job
from ze_core.proactive.notifier import ProactiveNotifier
from ze_personal.goals.planner import GoalPlanner
from ze_personal.goals.store import GoalStore
from ze_personal.goals.suggestion_store import GoalSuggestionStore
from ze_personal.goals.types import GoalSuggestion

log = get_logger(__name__)

_FIRST_SUGGESTION_INTRO = "Here's a goal idea, based on what I've learned about you:\n\n"


@proactive_job
class GoalSuggestionJob:
    job_id = "goal_suggestion"

    def __init__(
        self,
        notifier: ProactiveNotifier,
        goal_store: GoalStore,
        suggestion_store: GoalSuggestionStore,
        planner: GoalPlanner,
        memory_store: MemoryStore,
    ) -> None:
        self._notifier = notifier
        self._goal_store = goal_store
        self._suggestion_store = suggestion_store
        self._planner = planner
        self._memory_store = memory_store

    async def run(self) -> None:
        # 0. Expire stale PENDING suggestions so they don't hold the dedup window forever
        expired = await self._suggestion_store.expire_stale_pending(older_than_days=30)
        if expired:
            log.info("goal_suggestion_expired_stale", count=expired)

        # 1. Dedup: skip if a live suggestion (non-EXPIRED) was sent in last 6 days
        if await self._suggestion_store.was_suggested_recently(days=6):
            log.info("goal_suggestion_skipped_recent")
            return

        # 2. Gather signal — treat any read failure as insufficient signal
        try:
            facts    = await self._memory_store.list_recent_facts(days=90, limit=40)
            episodes = await self._memory_store.list_recent_episodes(days=30, limit=10)
            retros   = await self._goal_store.list_retrospectives(days=60)
            active   = await self._goal_store.list_active_goal_titles()
        except Exception as exc:
            log.error("goal_suggestion_signal_read_failed", error=str(exc))
            return

        # 3. Generate — confidence gate is inside generate_suggestion()
        suggestion = await self._planner.generate_suggestion(facts, episodes, retros, active)
        if suggestion is None:
            log.info("goal_suggestion_no_signal")
            return

        # 4. Check first-ness before saving (after save the record exists and would match)
        is_first = not await self._suggestion_store.was_suggested_recently(days=3650)

        # 5. Persist; week_key prevents concurrent double-save
        week_key = datetime.now(timezone.utc).strftime("%G-W%V")
        saved = await self._suggestion_store.save(suggestion, week_key)
        if not saved:
            log.info("goal_suggestion_week_conflict")
            return

        # 6. Push Telegram message; on failure immediately expire the record
        try:
            await self._push(suggestion, is_first=is_first)
        except Exception as exc:
            log.error("goal_suggestion_push_failed", error=str(exc))
            await self._suggestion_store.mark_expired(suggestion.id)
            return

        log.info("goal_suggestion_sent", suggestion_id=str(suggestion.id))

    async def _push(self, suggestion: GoalSuggestion, *, is_first: bool = False) -> None:
        short_id = suggestion.id.hex[:8]

        prefix = _FIRST_SUGGESTION_INTRO if is_first else ""
        content = (
            f"{prefix}"
            f"<b>{suggestion.title}</b>\n"
            f"{suggestion.objective}\n\n"
            f"<i>{suggestion.rationale}</i>"
        )
        await self._notifier.push_notification(Notification(
            content=content,
            format="html",
            urgency="normal",
            actions=[
                Action(label="Yes, create it", payload=f"goal_suggest:accept:{short_id}", row=0),
                Action(label="Dismiss",        payload=f"goal_suggest:dismiss:{short_id}", row=0),
                Action(label="Tell me more",   payload=f"goal_suggest:more:{short_id}",   row=1),
            ],
        ))
