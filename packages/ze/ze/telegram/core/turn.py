from __future__ import annotations

import asyncio

from ze.logging import get_logger
from ze.telegram.context import BotContext
from ze.telegram.core.delivery import deliver_response, keep_typing
from ze.telegram.handlers.confirmation import send_confirmation
from ze.telegram.handlers.workflow_plan import execute_dynamic_plan, send_plan_confirmation
from ze_core.interface.types import RawInput
from ze_core.progress import ProgressReporter

log = get_logger(__name__)


async def ingest_raw(ctx: BotContext, chat_id: int, raw: RawInput) -> None:
    """Preprocess transport input and run the conversation graph."""
    if ctx.interface is not None:
        ctx.interface.set_chat(chat_id)

    if ctx.container is None:
        log.error("ze_bot_missing_container", chat_id=chat_id)
        await ctx.bot.send_message(chat_id, "Internal error. Try again.")
        ctx.store.clear_active(chat_id)
        return

    await run_turn(ctx, chat_id, raw)


async def run_turn(ctx: BotContext, chat_id: int, raw: RawInput) -> None:
    config_extra: dict = {}
    progress_queue: asyncio.Queue[str] = asyncio.Queue()
    message_bucket: list[int] = []
    watcher_task: asyncio.Task | None = None

    if ctx.translations is not None:
        async def _enqueue(text: str) -> None:
            try:
                progress_queue.put_nowait(text)
            except asyncio.QueueFull:
                pass

        reporter = ProgressReporter(ctx.translations, sink=_enqueue)
        config_extra["reporter"] = reporter

        async def _progress_watcher() -> None:
            try:
                while True:
                    text = await progress_queue.get()
                    try:
                        msg = await ctx.bot.send_message(chat_id, text)
                        message_bucket.append(msg.message_id)
                    except Exception:
                        pass
            except asyncio.CancelledError:
                pass

        watcher_task = asyncio.create_task(_progress_watcher())

    typing_task = asyncio.create_task(keep_typing(ctx, chat_id))
    try:
        outcome = await ctx.container.invoke_raw_turn(
            str(chat_id),
            raw,
            config_extra=config_extra,
        )
    except Exception as exc:
        log.exception("graph_error", chat_id=chat_id, error=str(exc))
        ctx.store.clear_active(chat_id)
        await ctx.bot.send_message(chat_id, "Something went wrong. Try again.")
        return
    finally:
        typing_task.cancel()
        if watcher_task is not None and not watcher_task.done():
            watcher_task.cancel()
            await asyncio.gather(watcher_task, return_exceptions=True)
        for msg_id in message_bucket:
            try:
                await ctx.bot.delete_message(chat_id, msg_id)
            except Exception:
                pass

    await handle_turn_outcome(ctx, chat_id, outcome)


async def handle_turn_outcome(ctx: BotContext, chat_id: int, outcome) -> None:
    if outcome.error:
        ctx.store.clear_active(chat_id)
        await ctx.bot.send_message(chat_id, f"Error: {outcome.error}")
        return

    if outcome.interrupted:
        await send_confirmation(
            ctx,
            chat_id,
            outcome.draft,
            outcome.confirm_agent,
            outcome.confirm_action,
            outcome.config,
        )
        return

    if outcome.dynamic_plan_steps is not None:
        steps = outcome.dynamic_plan_steps
        high_risk = outcome.dynamic_plan_high_risk or []
        if not high_risk:
            await execute_dynamic_plan(ctx, chat_id, steps)
        else:
            await send_plan_confirmation(ctx, chat_id, steps, high_risk)
        return

    ctx.store.clear_active(chat_id)
    await deliver_response(ctx, chat_id, outcome.response or "")
    log.info("graph_complete", chat_id=chat_id)
