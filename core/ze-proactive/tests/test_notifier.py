from __future__ import annotations

from unittest.mock import AsyncMock

from ze_proactive.notifier import ProactiveNotifier
from ze_proactive.types import NotificationRow


def _make_row(**overrides):
    defaults = dict(
        id="notif-1",
        event_type="stuck_goal",
        source="goals",
        title="Goal stuck",
        body="Goal A hasn't moved in 3 days",
        target_type="goal",
        target_id="goal-a",
        created_at=None,
        read_at=None,
    )
    defaults.update(overrides)
    return NotificationRow(**defaults)


def make_notifier(store=None, interface=None):
    interface = interface or AsyncMock()
    store = store or AsyncMock()
    return (
        ProactiveNotifier(interface=interface, notification_store=store),
        interface,
        store,
    )


async def test_notify_persists_and_delivers():
    store = AsyncMock()
    store.create = AsyncMock(return_value=_make_row())
    notifier, interface, store = make_notifier(store=store)

    await notifier.notify(
        "stuck_goal",
        "Goal stuck",
        "Goal A hasn't moved",
        source="goals",
        target_type="goal",
        target_id="goal-a",
    )

    store.create.assert_called_once()
    interface.push.assert_called_once()


async def test_notify_skips_dedup_check_without_hours():
    store = AsyncMock()
    store.create = AsyncMock(return_value=_make_row())
    notifier, interface, store = make_notifier(store=store)

    await notifier.notify("morning_brief", "Brief", "body", source="personal")

    store.exists_recent.assert_not_called()
    store.create.assert_called_once()


async def test_notify_skips_persist_and_deliver_when_deduped():
    store = AsyncMock()
    store.exists_recent = AsyncMock(return_value=True)
    notifier, interface, store = make_notifier(store=store)

    await notifier.notify(
        "stuck_goal",
        "Goal stuck",
        "body",
        source="goals",
        target_type="goal",
        target_id="goal-a",
        hours=24,
    )

    store.create.assert_not_called()
    interface.push.assert_not_called()


async def test_notify_persists_and_delivers_when_not_deduped():
    store = AsyncMock()
    store.exists_recent = AsyncMock(return_value=False)
    store.create = AsyncMock(return_value=_make_row())
    notifier, interface, store = make_notifier(store=store)

    await notifier.notify(
        "stuck_goal",
        "Goal stuck",
        "body",
        source="goals",
        target_type="goal",
        target_id="goal-a",
        hours=24,
    )

    store.create.assert_called_once()
    interface.push.assert_called_once()


async def test_notify_no_store_logs_and_skips():
    interface = AsyncMock()
    notifier = ProactiveNotifier(interface=interface, notification_store=None)

    await notifier.notify("morning_brief", "Brief", "body", source="personal")

    interface.push.assert_not_called()


async def test_notify_swallows_push_failure():
    store = AsyncMock()
    store.create = AsyncMock(return_value=_make_row())
    interface = AsyncMock()
    interface.push = AsyncMock(side_effect=Exception("boom"))
    notifier = ProactiveNotifier(interface=interface, notification_store=store)

    await notifier.notify("morning_brief", "Brief", "body", source="personal")
