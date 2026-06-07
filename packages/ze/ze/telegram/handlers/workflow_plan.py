from __future__ import annotations

import asyncio

from aiogram.types import CallbackQuery

from ze_core.conversation import extract_response
from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.delivery import deliver_response, keep_typing
from ze.telegram.core.graph import make_workflow_config
from ze.telegram.keyboards import plan_confirmation_keyboard

log = get_logger(__name__)


async def send_plan_confirmation(
    ctx: BotContext,
    chat_id: int,
    steps: list,
    high_risk: list[int],
) -> None:
    lines = ["Ze will run the following steps:\n"]
    for i, step in enumerate(steps):
        marker = "⚠️ " if i in high_risk else ""
        lines.append(f"  {i + 1}. {marker}{step.task}")
    lines.append("\nProceed?")

    await ctx.bot.send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=plan_confirmation_keyboard(),
    )

    timeout_task = asyncio.create_task(plan_approval_timeout(ctx, chat_id))
    ctx.store.clear_active(chat_id)
    ctx.store.set_pending_plan(chat_id, steps, timeout_task)
    log.info("awaiting_plan_approval", chat_id=chat_id, steps=len(steps), high_risk=high_risk)


async def handle_plan_callback(ctx: BotContext, query: CallbackQuery) -> None:
    chat_id = query.message.chat.id
    decision = (query.data or "").split(":", 1)[1]
    await query.answer()
    await query.message.edit_reply_markup(reply_markup=None)

    steps, timeout_task = ctx.store.get_pending_plan(chat_id)
    if timeout_task:
        timeout_task.cancel()

    if decision == "yes" and steps:
        ctx.store.cancel_plan_task(chat_id)
        ctx.store.mark_active(chat_id)
        asyncio.create_task(execute_dynamic_plan(ctx, chat_id, steps))
    else:
        ctx.store.cancel_plan_task(chat_id)
        ctx.store.clear_active(chat_id)
        await ctx.bot.send_message(
            chat_id,
            "Plan cancelled. What would you like to change?",
        )


async def execute_dynamic_plan(ctx: BotContext, chat_id: int, steps: list) -> None:
    execution_id = await ctx.workflow_store.start_execution(None)
    thread_id = str(execution_id)
    config = make_workflow_config(ctx, thread_id)

    state = {
        "prompt": "",
        "session_id": str(chat_id),
        "session_overrides": {},
        "input_modality": "text",
        "image_data": None,
        "image_mime": None,
        "image_caption": None,
        "envelope": None,
        "memory_context": None,
        "agent_context": None,
        "gate_decision": None,
        "agent_result": None,
        "subtask_results": [],
        "pending_confirmation": False,
        "final_response": None,
        "error": None,
        "messages": [],
        "last_active_at": None,
        "workflow_id": None,
        "workflow_execution_id": execution_id,
        "workflow_steps": steps,
        "current_step_index": 0,
        "workflow_step_results": [],
        "dynamic_plan_steps": None,
        "dynamic_plan_high_risk": [],
    }

    typing_task = asyncio.create_task(keep_typing(ctx, chat_id))
    try:
        final_state = await ctx.workflow_graph.ainvoke(state, config)
    except Exception as exc:
        log.exception("dynamic_plan_exec_error", chat_id=chat_id, error=str(exc))
        ctx.store.clear_active(chat_id)
        await ctx.bot.send_message(chat_id, "Something went wrong executing the plan. Try again.")
        return
    finally:
        typing_task.cancel()

    response = extract_response(final_state)
    ctx.store.clear_active(chat_id)
    await deliver_response(ctx, chat_id, response)
    log.info("dynamic_plan_complete", chat_id=chat_id, execution_id=str(execution_id))


async def plan_approval_timeout(ctx: BotContext, chat_id: int) -> None:
    try:
        await asyncio.sleep(ctx.settings.confirm_timeout_seconds)
        ctx.store.cancel_plan_task(chat_id)
        ctx.store.clear_active(chat_id)
        await ctx.bot.send_message(
            chat_id,
            "⏱ Plan approval timed out. The plan was cancelled.",
        )
        log.info("plan_approval_expired", chat_id=chat_id)
    except asyncio.CancelledError:
        pass
