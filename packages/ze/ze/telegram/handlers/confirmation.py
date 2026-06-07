from __future__ import annotations

import asyncio

from aiogram.types import CallbackQuery, ForceReply

from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.graph import resume_graph
from ze_core.interface.types import ConfirmationRequest

log = get_logger(__name__)


async def send_confirmation(
    ctx: BotContext,
    chat_id: int,
    draft: str,
    agent: str,
    action: str,
    config: dict,
) -> None:
    if ctx.interface is not None:
        ctx.interface.set_chat(chat_id)
        await ctx.interface.send_confirmation(
            ConfirmationRequest(
                content=draft,
                options=["Approve", "Cancel", "Edit"],
                editable=True,
                timeout_seconds=ctx.settings.confirm_timeout_seconds,
            ),
            agent=agent,
            action=action,
        )
    else:
        await ctx.bot.send_message(chat_id, draft or "Confirm?")

    timeout_task = asyncio.create_task(
        confirmation_timeout(ctx, chat_id, config)
    )
    ctx.store.clear_active(chat_id)
    ctx.store.set_pending_confirmation(chat_id, config, timeout_task)
    log.info("awaiting_confirmation", chat_id=chat_id, agent=agent)


async def confirmation_timeout(ctx: BotContext, chat_id: int, config: dict) -> None:
    try:
        await asyncio.sleep(ctx.settings.confirm_timeout_seconds)
        await ctx.graph.aupdate_state(config, {"error": "confirmation_expired"})
        ctx.store.clear_all(chat_id)
        await ctx.bot.send_message(
            chat_id,
            "⏱ Confirmation expired. The action was cancelled.",
        )
        log.info("confirmation_expired", chat_id=chat_id)
    except asyncio.CancelledError:
        pass


async def handle_confirmation(ctx: BotContext, query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    data = query.data or ""

    if not data.startswith("confirm:"):
        await query.answer()
        return

    decision = data.split(":", 1)[1]
    await query.answer()

    await query.message.edit_reply_markup(reply_markup=None)

    if decision == "edit":
        ctx.store.set_awaiting_edit(chat_id)
        await ctx.bot.send_message(
            chat_id,
            "Please reply with your edited version:",
            reply_markup=ForceReply(selective=True),
        )
        return

    await resume_graph(ctx, chat_id, decision)
