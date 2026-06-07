from __future__ import annotations

import asyncio
import html as _html
from uuid import UUID

from aiogram.types import CallbackQuery, ForceReply

from ze.logging import get_logger
from ze.telegram.context import BotContext

log = get_logger(__name__)


async def approve_gate(
    ctx: BotContext,
    gate_id: UUID,
    query: CallbackQuery | None = None,
    *,
    goal_title: str | None = None,
) -> None:
    if not ctx.goal_executor:
        if query is not None:
            await query.answer()
        return

    if query is not None:
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

    asyncio.create_task(ctx.goal_executor.handle_gate_approved(gate_id))

    if goal_title is not None and query is not None:
        await query.message.answer(
            f"Approved — Ze will continue <b>{_html.escape(goal_title)}</b>.",
            parse_mode="HTML",
        )


async def stop_gate(
    ctx: BotContext,
    gate_id: UUID,
    query: CallbackQuery | None = None,
    *,
    goal_title: str | None = None,
) -> None:
    if not ctx.goal_executor:
        if query is not None:
            await query.answer()
        return

    if query is not None:
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

    asyncio.create_task(ctx.goal_executor.handle_gate_stopped(gate_id))

    if goal_title is not None and query is not None:
        await query.message.answer(
            f"Stopped <b>{_html.escape(goal_title)}</b>.",
            parse_mode="HTML",
        )


async def redirect_gate(
    ctx: BotContext,
    chat_id: int,
    gate_id: UUID,
    query: CallbackQuery | None = None,
) -> None:
    if query is not None:
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)

    ctx.store.set_awaiting_goal_redirect(chat_id, str(gate_id))
    await ctx.bot.send_message(
        chat_id,
        "Send your new instructions for this goal:",
        reply_markup=ForceReply(selective=True),
    )


async def handle_goal_gate(ctx: BotContext, query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    data = query.data or ""
    parts = data.split(":", 2)

    if len(parts) != 3 or not ctx.goal_executor:
        await query.answer()
        return

    action, gate_id_str = parts[1], parts[2]

    try:
        gate_id = UUID(gate_id_str)
    except ValueError:
        await query.answer()
        return

    if action == "approve":
        await approve_gate(ctx, gate_id, query)
    elif action == "stop":
        await stop_gate(ctx, gate_id, query)
    elif action == "redirect":
        await redirect_gate(ctx, chat_id, gate_id, query)
    else:
        await query.answer()


async def handle_goal_redirect_reply(
    ctx: BotContext,
    chat_id: int,
    gate_id_str: str,
    text: str,
) -> None:
    ctx.store.clear_awaiting_goal_redirect(chat_id)
    if not ctx.goal_executor:
        return
    asyncio.create_task(ctx.goal_executor.handle_gate_redirected(UUID(gate_id_str), text))
    await ctx.bot.send_message(chat_id, "Got it — replanning and continuing.")


async def approve_gate_for_goal(ctx: BotContext, query: CallbackQuery, goal) -> None:
    if not ctx.goal_executor or not ctx.goal_store:
        await query.answer()
        return
    gate = await ctx.goal_store.get_pending_gate(goal.id)
    if gate is None:
        await query.answer("Gate already resolved.", show_alert=False)
        return
    await approve_gate(ctx, gate.id, query, goal_title=goal.title)


async def stop_gate_for_goal(ctx: BotContext, query: CallbackQuery, goal) -> None:
    if not ctx.goal_executor or not ctx.goal_store:
        await query.answer()
        return
    gate = await ctx.goal_store.get_pending_gate(goal.id)
    if gate is None:
        await query.answer("Gate already resolved.", show_alert=False)
        return
    await stop_gate(ctx, gate.id, query, goal_title=goal.title)
