from __future__ import annotations

import asyncio

from ze_core.conversation import extract_response, make_graph_input_from_raw_text
from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.delivery import deliver_response, keep_typing
from ze_core.interface.types import RawInput

log = get_logger(__name__)


def make_config(ctx: BotContext, chat_id: int | str) -> dict:
    if ctx.container is not None:
        return ctx.container._build_config(chat_id)
    return {
        "configurable": {
            "thread_id": str(chat_id),
            "router": ctx.router,
            "capability_gate": ctx.capability_gate,
            "memory_store": ctx.memory_store,
            "persona_store": ctx.persona_store,
            "person_store": ctx.person_store,
            "openrouter_client": ctx.openrouter_client,
            "embedder": ctx.embedder,
            "settings": ctx.settings,
            "workflow_planner": ctx.workflow_planner,
            "contact_channel_store": ctx.contact_channel_store,
            "interface": ctx.interface,
        }
    }


def make_workflow_config(ctx: BotContext, thread_id: str) -> dict:
    return {
        "configurable": {
            "thread_id": thread_id,
            "router": ctx.router,
            "capability_gate": ctx.capability_gate,
            "memory_store": ctx.memory_store,
            "persona_store": ctx.persona_store,
            "openrouter_client": ctx.openrouter_client,
            "embedder": ctx.embedder,
            "settings": ctx.settings,
            "workflow_store": ctx.workflow_store,
        }
    }


async def reset_session(ctx: BotContext, chat_id: int) -> None:
    config = make_config(ctx, chat_id)
    await ctx.graph.aupdate_state(config, {"messages": [], "last_active_at": None})
    ctx.store.clear_all(chat_id)
    log.info("session_reset", chat_id=chat_id)


async def handle_cancel(ctx: BotContext, chat_id: int) -> None:
    if ctx.container is None:
        await ctx.bot.send_message(chat_id, "Nothing to cancel.")
        return
    await ctx.container.abort_invocation(str(chat_id), reason="user cancelled")
    log.info("user_cancel", chat_id=chat_id)
    await ctx.bot.send_message(chat_id, "Cancelling...")


async def handle_edit_reply(ctx: BotContext, chat_id: int, text: str) -> None:
    ctx.store.clear_awaiting_edit(chat_id)
    ctx.store.cancel_confirm_task(chat_id)
    log.info("edit_reply_received", chat_id=chat_id)
    await resume_graph(ctx, chat_id, "edit", edit_content=text)


async def resume_graph(
    ctx: BotContext,
    chat_id: int,
    decision: str,
    edit_content: str | None = None,
) -> None:
    ctx.store.cancel_confirm_task(chat_id)
    config = ctx.store.get_pending_config(chat_id)
    if config is None:
        await ctx.bot.send_message(chat_id, "No pending confirmation.")
        return

    ctx.store.mark_active(chat_id)

    if decision == "no":
        ctx.store.clear_all(chat_id)
        await ctx.bot.send_message(chat_id, "Action cancelled.")
        return

    if decision == "edit" and edit_content is not None:
        await ctx.graph.aupdate_state(
            config,
            {"agent_result": None, "prompt": edit_content},
        )

    typing_task = asyncio.create_task(keep_typing(ctx, chat_id))
    try:
        if ctx.container is not None:
            outcome = await ctx.container.resume_turn(config)
            response = outcome.response or ""
        else:
            final_state = await ctx.graph.ainvoke(None, config)
            response = extract_response(final_state)
    except Exception as exc:
        log.exception("resume_error", chat_id=chat_id, error=str(exc))
        ctx.store.clear_all(chat_id)
        await ctx.bot.send_message(chat_id, "Something went wrong. Try again.")
        return
    finally:
        typing_task.cancel()

    ctx.store.clear_all(chat_id)
    await deliver_response(ctx, chat_id, response)
    log.info("resume_complete", chat_id=chat_id)


async def invoke(ctx: BotContext, prompt: str, session_id: str) -> dict:
    """Invoke the graph directly for eval/testing. Returns raw final state."""
    eval_session = f"eval-{session_id}"
    if ctx.container is not None:
        outcome = await ctx.container.invoke_raw_turn(
            eval_session,
            RawInput(text=prompt),
        )
        return outcome.final_state

    state = make_graph_input_from_raw_text(prompt, eval_session)
    config = make_config(ctx, eval_session)
    return await ctx.graph.ainvoke(state, config)
