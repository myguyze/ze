from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ze_calendar.api.schemas import PluginPageResponse, ReminderListItem
from ze_calendar.ui.page import build_reminders_page
from ze_plugin.api_auth import require_api_key

router = APIRouter(prefix="/api/v0", tags=["reminders"], dependencies=[Depends(require_api_key)])


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


@router.get(
    "/reminders/page",
    response_model=PluginPageResponse,
    operation_id="getRemindersPage",
    summary="Reminders overview page",
    description="Returns the server-driven UI tree for the reminders management screen.",
)
async def get_reminders_page(request: Request) -> PluginPageResponse:
    store = request.app.state.container._plugin_stores.get("reminder_store")
    if store is None:
        return PluginPageResponse(title="Upcoming", tree=build_reminders_page([]))

    reminders = await store.list_all()
    return PluginPageResponse(
        title="Upcoming",
        tree=build_reminders_page(reminders),
    )
