from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from ze.logging import get_logger

log = get_logger(__name__)

router = APIRouter(tags=["telegram"])


@router.post(
    "/telegram/webhook",
    status_code=status.HTTP_200_OK,
    summary="Telegram webhook",
    description="Receives updates from the Telegram Bot API.",
    include_in_schema=False,
)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    settings = request.app.state.settings
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    body = await request.json()
    update = Update(**body)

    chat_id = _extract_chat_id(update)
    if chat_id is None or chat_id != settings.telegram_allowed_chat_id:
        return {}

    ze_bot = request.app.state.ze_bot

    if update.message:
        if update.message.text:
            await ze_bot.handle_message(update.message)
        elif update.message.voice or update.message.audio:
            await ze_bot.handle_voice(update.message)
        elif update.message.photo:
            await ze_bot.handle_photo(update.message)
    elif update.callback_query:
        await ze_bot.handle_callback(update.callback_query)

    return {}


def _extract_chat_id(update: Update) -> int | None:
    if update.message:
        return update.message.chat.id
    if update.callback_query and update.callback_query.message:
        return update.callback_query.message.chat.id
    return None
