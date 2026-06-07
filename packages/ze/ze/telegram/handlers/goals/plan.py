from __future__ import annotations

import html as _html
from uuid import UUID

from aiogram.types import CallbackQuery

from ze.telegram.context import BotContext


async def handle_goal_plan(ctx: BotContext, query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    data = query.data or ""
    parts = data.split(":", 2)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)

    if len(parts) != 3 or not ctx.goal_executor or not ctx.goal_store:
        return

    action, goal_id_str = parts[1], parts[2]
    goal_id = UUID(goal_id_str)
    goal = await ctx.goal_store.get_goal(goal_id)

    if action == "yes":
        ok = await ctx.goal_executor.approve_plan(goal_id)
        if ok and goal:
            await ctx.bot.send_message(
                chat_id,
                f"✅ Goal <b>{_html.escape(goal.title)}</b> started.",
                parse_mode="HTML",
            )
        else:
            await ctx.bot.send_message(chat_id, "That goal is no longer awaiting approval.")
    elif action == "no":
        ok = await ctx.goal_executor.reject_plan(goal_id)
        if ok and goal:
            await ctx.bot.send_message(
                chat_id,
                f"❌ Goal <b>{_html.escape(goal.title)}</b> cancelled.",
                parse_mode="HTML",
            )
        else:
            await ctx.bot.send_message(chat_id, "That goal is no longer awaiting approval.")
