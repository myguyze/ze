from __future__ import annotations

from uuid import UUID

from aiogram.types import CallbackQuery

from ze.telegram.context import BotContext
from ze.telegram.core.delivery import send_html
from ze.telegram.formatting import bold


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
            await send_html(ctx, chat_id, f"✅ Goal {bold(goal.title)} started.")
        else:
            await send_html(ctx, chat_id, "That goal is no longer awaiting approval.")
    elif action == "no":
        ok = await ctx.goal_executor.reject_plan(goal_id)
        if ok and goal:
            await send_html(ctx, chat_id, f"❌ Goal {bold(goal.title)} cancelled.")
        else:
            await send_html(ctx, chat_id, "That goal is no longer awaiting approval.")
