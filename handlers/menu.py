from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.main import main_menu
from texts import WELCOME

router = Router(name="menu")


@router.callback_query(F.data == "main:home")
async def home(callback: CallbackQuery) -> None:
    await callback.message.edit_text(WELCOME, reply_markup=main_menu())
    await callback.answer()
