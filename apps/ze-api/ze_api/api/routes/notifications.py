from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ze_api.api.dependencies import get_notification_store, require_api_key
from ze_api.api.schemas import (
    MarkAllReadResponse,
    NotificationItem,
    NotificationListResponse,
    UnreadCountResponse,
)
from ze_proactive.notification_store import InvalidCursorError

router = APIRouter(
    prefix="/notifications",
    tags=["notifications"],
    dependencies=[Depends(require_api_key)],
)


@router.get(
    "",
    response_model=NotificationListResponse,
    operation_id="listNotifications",
    summary="List notifications",
    description=(
        "Reverse-chronological, cursor-paginated notification history. "
        "Set mark_read=true to atomically mark the returned page as read "
        "(used by the panel-open fetch)."
    ),
)
async def list_notifications(
    cursor: str | None = None,
    limit: int = 20,
    unread_only: bool = False,
    mark_read: bool = False,
    notification_store=Depends(get_notification_store),
) -> NotificationListResponse:
    try:
        items, next_cursor = await notification_store.list_page(
            cursor=cursor,
            limit=limit,
            unread_only=unread_only,
            mark_read=mark_read,
        )
    except InvalidCursorError:
        raise HTTPException(status_code=400, detail="Invalid cursor")

    return NotificationListResponse(
        items=[NotificationItem(**vars(n)) for n in items],
        next_cursor=next_cursor,
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    operation_id="getUnreadNotificationCount",
    summary="Get unread notification count",
    description="Returns the number of unread notifications, for the bell badge.",
)
async def get_unread_count(
    notification_store=Depends(get_notification_store),
) -> UnreadCountResponse:
    count = await notification_store.unread_count()
    return UnreadCountResponse(count=count)


@router.post(
    "/{notification_id}/read",
    status_code=204,
    operation_id="markNotificationRead",
    summary="Mark a notification read",
    description="Marks a single notification read. Idempotent.",
)
async def mark_notification_read(
    notification_id: str,
    notification_store=Depends(get_notification_store),
) -> None:
    found = await notification_store.mark_read(notification_id)
    if not found:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    operation_id="markAllNotificationsRead",
    summary="Mark all notifications read",
    description="Marks every currently-unread notification read.",
)
async def mark_all_notifications_read(
    notification_store=Depends(get_notification_store),
) -> MarkAllReadResponse:
    marked = await notification_store.mark_all_read()
    return MarkAllReadResponse(marked=marked)
