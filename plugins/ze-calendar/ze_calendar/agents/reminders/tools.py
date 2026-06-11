from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ze_core.orchestration.tool import ToolAccess, tool
from ze_core.proactive.notifier import ProactiveNotifier
from ze_calendar.reminders.store import ReminderStore, fire_reminder
from ze_personal.workflow.scheduler import WorkflowScheduler


@tool(access=ToolAccess.WRITE, description="Set a new reminder. fire_at must be an ISO-8601 UTC datetime string.")
async def set_reminder(
    store: ReminderStore,
    scheduler: WorkflowScheduler,
    notifier: ProactiveNotifier,
    label: str,
    fire_at: str,
) -> dict:
    now = datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(fire_at)
        fire_dt = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return {"error": "Could not parse fire_at. Use ISO-8601 format, e.g. 2025-05-28T15:00:00Z."}

    if fire_dt <= now:
        return {"error": "fire_at is in the past. Provide a future datetime."}

    rid = await store.create(label=label, fire_at=fire_dt)
    scheduler.schedule_at(
        fn=fire_reminder,
        dt=fire_dt,
        job_id=f"user_reminder:{rid}",
        args=(store, notifier, rid),
    )
    return {"id": str(rid), "label": label, "fire_at": fire_dt.isoformat()}


@tool(access=ToolAccess.READ, description="List all pending (unsent, future) reminders.")
async def list_reminders(store: ReminderStore) -> list:
    pending = await store.list_pending()
    return [
        {
            "id": str(r.id),
            "label": r.label,
            "fire_at": r.fire_at.isoformat(),
        }
        for r in pending
    ]


@tool(access=ToolAccess.WRITE, description="Cancel a pending reminder by its ID. Call list_reminders first to find the ID.")
async def cancel_reminder(store: ReminderStore, scheduler: WorkflowScheduler, reminder_id: str) -> dict:
    try:
        uid = UUID(reminder_id)
    except ValueError:
        return {"error": f"Invalid reminder ID: {reminder_id!r}"}

    reminder = await store.get(uid)
    if reminder is None:
        return {"error": f"No reminder found with ID {reminder_id}."}

    scheduler.remove_job_if_exists(f"user_reminder:{uid}")
    await store.delete(uid)
    return {"cancelled": reminder.label}
