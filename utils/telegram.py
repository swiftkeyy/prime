from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message


async def safe_callback_answer(callback: CallbackQuery, text: str | None = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text=text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        error_text = str(exc).lower()
        if (
            "query is too old" in error_text
            or "query id is invalid" in error_text
            or "response timeout expired" in error_text
        ):
            return
        raise


async def safe_edit_message(message: Message | None, text: str, reply_markup=None, **kwargs) -> bool:
    if message is None:
        return False
    try:
        await message.edit_text(text, reply_markup=reply_markup, **kwargs)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def safe_edit_callback(callback: CallbackQuery, text: str, reply_markup=None, **kwargs) -> bool:
    return await safe_edit_message(callback.message, text, reply_markup=reply_markup, **kwargs)
