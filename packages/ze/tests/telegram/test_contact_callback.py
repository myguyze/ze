from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from ze_personal.contacts.types import Person
from ze.telegram.handlers.contacts import handle_contact_callback
from ze.telegram.keyboards import contact_confirmation_keyboard
from tests.telegram.conftest import make_ctx, make_query


def test_contact_confirmation_keyboard_callback_data():
    pid = uuid4()
    kb = contact_confirmation_keyboard(pid)
    buttons = kb.inline_keyboard[0]
    assert len(buttons) == 2
    assert buttons[0].callback_data == f"contact:confirm:{pid}"
    assert buttons[1].callback_data == f"contact:dismiss:{pid}"


def test_contact_confirmation_keyboard_fits_telegram_limit():
    pid = uuid4()
    kb = contact_confirmation_keyboard(pid)
    for row in kb.inline_keyboard:
        for btn in row:
            assert len(btn.callback_data.encode()) <= 64


def _make_contact_ctx(person_store):
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return make_ctx(bot=bot, person_store=person_store), bot


async def test_confirm_callback_confirms_and_acks():
    pid = uuid4()
    person = Person(id=pid, name="João Silva", confirmed=False, dismissed=False, confidence=0.9)

    store = AsyncMock()
    store.confirm = AsyncMock(return_value=person)

    ctx, bot = _make_contact_ctx(store)
    query = make_query(f"contact:confirm:{pid}")

    await handle_contact_callback(ctx, query)

    store.confirm.assert_awaited_once_with(pid)
    bot.send_message.assert_awaited_once()
    text = bot.send_message.call_args[0][1]
    assert "João Silva" in text


async def test_dismiss_callback_dismisses_silently():
    pid = uuid4()

    store = AsyncMock()
    store.dismiss = AsyncMock()

    ctx, bot = _make_contact_ctx(store)
    query = make_query(f"contact:dismiss:{pid}")

    await handle_contact_callback(ctx, query)

    store.dismiss.assert_awaited_once_with(pid)
    bot.send_message.assert_not_awaited()


async def test_confirm_callback_handles_not_found():
    pid = uuid4()

    store = AsyncMock()
    store.confirm = AsyncMock(side_effect=ValueError("not found"))

    ctx, bot = _make_contact_ctx(store)
    query = make_query(f"contact:confirm:{pid}")

    await handle_contact_callback(ctx, query)

    bot.send_message.assert_awaited_once()
    text = bot.send_message.call_args[0][1]
    assert "not found" in text.lower()


async def test_invalid_uuid_is_ignored():
    store = AsyncMock()
    ctx, bot = _make_contact_ctx(store)
    query = make_query("contact:confirm:not-a-uuid")

    await handle_contact_callback(ctx, query)

    store.confirm.assert_not_awaited()
    bot.send_message.assert_not_awaited()


async def test_unknown_action_is_ignored():
    pid = uuid4()
    store = AsyncMock()
    ctx, bot = _make_contact_ctx(store)
    query = make_query(f"contact:merge:{pid}")

    await handle_contact_callback(ctx, query)

    store.confirm.assert_not_awaited()
    store.dismiss.assert_not_awaited()
