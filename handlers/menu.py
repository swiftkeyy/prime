from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.main import main_menu
from texts import WELCOME
from utils.telegram import safe_callback_answer, safe_edit_callback

router = Router(name="menu")


@router.callback_query(F.data == "main:home")
async def home(callback: CallbackQuery) -> None:
    await safe_edit_callback(callback, WELCOME, reply_markup=main_menu())
    await safe_callback_answer(callback)
