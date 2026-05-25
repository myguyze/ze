from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def contact_confirmation_keyboard(person_id: UUID) -> InlineKeyboardMarkup:
    pid = str(person_id)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Add", callback_data=f"contact:confirm:{pid}"),
        InlineKeyboardButton(text="❌ Skip", callback_data=f"contact:dismiss:{pid}"),
    ]])


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


def goal_plan_confirmation_keyboard(goal_id: UUID) -> InlineKeyboardMarkup:
    gid = str(goal_id)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Start goal", callback_data=f"goal_plan:yes:{gid}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"goal_plan:no:{gid}"),
    ]])
