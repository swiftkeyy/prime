from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import Settings
from texts import SUPPORT

router = Router(name="support")


@router.callback_query(F.data == "support:open")
async def support(callback: CallbackQuery, settings: Settings) -> None:
    kb = InlineKeyboardBuilder()
    support_username = settings.SUPPORT_USERNAME.lstrip("@")
    if support_username:
        kb.button(text="💬 Написать оператору", url=f"https://t.me/{support_username}")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    await callback.message.edit_text(SUPPORT, reply_markup=kb.as_markup())
    await callback.answer()
