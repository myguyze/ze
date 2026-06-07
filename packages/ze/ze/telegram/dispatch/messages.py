from __future__ import annotations

from aiogram.types import Message

from ze.logging import get_logger
from ze.telegram.commands import costs_summary, memory_summary
from ze.telegram.context import BotContext
from ze.telegram.core.graph import handle_cancel, handle_edit_reply, reset_session
from ze.telegram.core.turn import ingest_raw
from ze.telegram.handlers.contacts import handle_contacts_command
from ze.telegram.handlers.goals.gates import handle_goal_redirect_reply
from ze.telegram.handlers.persona import handle_persona_command
from ze_core.interface.types import RawInput
from ze_core.telemetry.context import set_flow_context

log = get_logger(__name__)


async def dispatch_message(ctx: BotContext, message: Message) -> None:
    chat_id = message.chat.id
    text = message.text or ""

    if ctx.store.is_awaiting_edit(chat_id):
        await handle_edit_reply(ctx, chat_id, text)
        return

    gate_id = ctx.store.get_awaiting_goal_redirect(chat_id)
    if gate_id is not None and text:
        await handle_goal_redirect_reply(ctx, chat_id, gate_id, text)
        return

    if ctx.store.is_active(chat_id):
        await ctx.bot.send_message(chat_id, "A task is already in progress.")
        return

    if text == "/new":
        await reset_session(ctx, chat_id)
        await ctx.bot.send_message(
            chat_id,
            "Session reset. Starting fresh — I still remember what I know about you.",
        )
        return

    if text == "/cancel":
        await handle_cancel(ctx, chat_id)
        return

    if text == "/costs":
        summary = await costs_summary(ctx.pool)
        await ctx.bot.send_message(chat_id, summary, parse_mode="HTML")
        return

    if text == "/memory":
        summary = await memory_summary(ctx.pool)
        await ctx.bot.send_message(chat_id, summary, parse_mode="HTML")
        return

    if text == "/persona" or text.startswith("/persona "):
        await handle_persona_command(ctx, chat_id, text)
        return

    if text == "/contacts" or text.startswith("/contacts "):
        await handle_contacts_command(ctx, chat_id, text)
        return

    ctx.store.mark_active(chat_id)
    set_flow_context("user_message", str(chat_id))
    log.info("message_received", chat_id=chat_id)
    await ingest_raw(ctx, chat_id, RawInput(text=text or None))
