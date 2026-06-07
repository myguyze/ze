from __future__ import annotations

from uuid import UUID

from aiogram.types import CallbackQuery

from ze.telegram.context import BotContext
from ze.telegram.handlers.goals.gates import approve_gate_for_goal, stop_gate_for_goal
from ze.telegram.core.delivery import answer_html
from ze.telegram.formatting import bold
from ze_personal.goals.types import GoalStatus


async def handle_stuck(ctx: BotContext, query: CallbackQuery) -> None:
    data = query.data or ""
    parts = data.split(":", 2)
    if len(parts) != 3:
        await query.answer()
        return

    _, action, goal_id_hex = parts
    try:
        goal_id = UUID(goal_id_hex)
    except ValueError:
        await query.answer("Invalid goal reference.")
        return

    if not ctx.goal_store:
        await query.answer()
        return

    goal = await ctx.goal_store.get_goal(goal_id)
    if goal is None:
        await query.answer("Goal not found.")
        return

    if action == "redirect":
        await stuck_redirect(query, goal)
    elif action == "pause":
        await stuck_pause(ctx, query, goal)
    elif action == "abandon":
        await stuck_abandon(ctx, query, goal)
    elif action == "gate_approve":
        await approve_gate_for_goal(ctx, query, goal)
    elif action == "gate_stop":
        await stop_gate_for_goal(ctx, query, goal)
    else:
        await query.answer()


async def stuck_redirect(query: CallbackQuery, goal) -> None:
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)
    await answer_html(
        query.message,
        f"Send me your instructions for {bold(goal.title)} "
        f"and I'll redirect it right away.",
    )


async def stuck_pause(ctx: BotContext, query: CallbackQuery, goal) -> None:
    if goal.status not in (GoalStatus.ACTIVE, GoalStatus.AWAITING_GATE):
        await query.answer("Already resolved.", show_alert=False)
        return
    await ctx.goal_store.update_status(goal.id, GoalStatus.PAUSED)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)
    await answer_html(
        query.message,
        f"Paused {bold(goal.title)}. Resume it any time by telling me.",
    )


async def stuck_abandon(ctx: BotContext, query: CallbackQuery, goal) -> None:
    if goal.status in (GoalStatus.COMPLETED, GoalStatus.ABANDONED):
        await query.answer("Already resolved.", show_alert=False)
        return
    await ctx.goal_store.update_status(goal.id, GoalStatus.ABANDONED)
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)
    await answer_html(query.message, f"Abandoned {bold(goal.title)}.")

