"""Local development entry point — Telegram long-polling.

Replaces the webhook with long-polling so you can interact with the bot
locally without a public URL. Run via `make dev-poll`.

Calling delete_webhook on startup steals delivery from any running webhook
(e.g. a Fly.io deploy), so messages go to your local process instead.
Stop polling (Ctrl-C) to hand delivery back — re-deploy or call set_webhook
again to restore the production webhook.
"""

import asyncio

from ze.container import build_container
from ze.logging import configure_logging, get_logger
from ze.settings import get_settings

log = get_logger(__name__)


def _chat_id(update) -> int | None:
    if update.message:
        return update.message.chat.id
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat.id
    return None


async def _poll(container) -> None:
    bot = container.bot
    ze_bot = container.ze_bot
    allowed = container.settings.telegram_allowed_chat_id

    await bot.delete_webhook(drop_pending_updates=True)
    log.info("polling_started", allowed_chat_id=allowed)
    print(f"Polling — send a message to your bot in Telegram (chat_id={allowed})")

    offset = 0
    while True:
        updates = await bot.get_updates(
            offset=offset,
            timeout=30,
            allowed_updates=["message", "callback_query"],
        )
        for update in updates:
            offset = update.update_id + 1
            if _chat_id(update) != allowed:
                continue
            if update.message and update.message.text:
                await ze_bot.handle_message(update.message)
            elif update.callback_query:
                await ze_bot.handle_callback(update.callback_query)


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    container = await build_container(settings)
    try:
        await _poll(container)
    except asyncio.CancelledError:
        pass
    finally:
        await container.close()
        log.info("polling_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
