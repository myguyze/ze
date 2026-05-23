from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def persona_keyboard(profiles: list[str], active: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=f"{p} ✓" if p == active else p,
            callback_data=f"persona:profile:{p}",
        )
        for p in profiles
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes", callback_data="confirm:yes"),
        InlineKeyboardButton(text="❌ No", callback_data="confirm:no"),
        InlineKeyboardButton(text="✏️ Edit", callback_data="confirm:edit"),
    ]])


def plan_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes, run it", callback_data="plan:yes"),
        InlineKeyboardButton(text="❌ No", callback_data="plan:no"),
    ]])
