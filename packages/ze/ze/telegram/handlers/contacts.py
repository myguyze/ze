from __future__ import annotations

import html as _html
from uuid import UUID

from aiogram.types import CallbackQuery

from ze.telegram.commands import contacts_search, contacts_summary
from ze.telegram.context import BotContext


async def handle_contacts_command(ctx: BotContext, chat_id: int, text: str) -> None:
    query = text[len("/contacts"):].strip()
    if query:
        summary = await contacts_search(ctx.person_store, query)
    else:
        summary = await contacts_summary(ctx.person_store)
    await ctx.bot.send_message(chat_id, summary, parse_mode="HTML")


async def handle_contact_callback(ctx: BotContext, query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    data = query.data or ""
    parts = data.split(":", 2)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)

    if len(parts) != 3 or not ctx.person_store:
        return

    action, person_id_str = parts[1], parts[2]
    try:
        person_id = UUID(person_id_str)
    except ValueError:
        return

    if action == "confirm":
        try:
            person = await ctx.person_store.confirm(person_id)
            await ctx.bot.send_message(
                chat_id,
                f"✅ Added <b>{_html.escape(person.name)}</b> to your contacts.",
                parse_mode="HTML",
            )
        except ValueError:
            await ctx.bot.send_message(chat_id, "Contact not found.")
    elif action == "dismiss":
        await ctx.person_store.dismiss(person_id)
