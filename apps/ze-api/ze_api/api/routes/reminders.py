from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ze_api.api.dependencies import require_api_key
from ze_api.api.schemas import ReminderListItem

router = APIRouter(tags=["reminders"], dependencies=[Depends(require_api_key)])


@router.get(
    "/reminders",
    response_model=list[ReminderListItem],
    operation_id="listReminders",
    summary="List reminders",
    description="Returns user reminders for the web client reminders screen.",
)
async def list_reminders(request: Request) -> list[ReminderListItem]:
    store = request.app.state.container._plugin_stores.get("reminder_store")
    if store is None:
        return []

    reminders = await store.list_all()
    return [
        ReminderListItem(
            id=reminder.id,
            label=reminder.label,
            fire_at=reminder.fire_at,
            fired=reminder.sent,
        )
        for reminder in reminders
    ]
