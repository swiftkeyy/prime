from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from database.models import User
from keyboards.filters import filters_menu as filters_kb
from texts import filters_menu

router = Router(name="filters")


async def render(callback: CallbackQuery, user: User, notice: str | None = None) -> None:
    try:
        await callback.message.edit_text(
            filters_menu(user),
            reply_markup=filters_kb(user.digits_enabled, user.underscore_enabled),
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer(notice)


@router.callback_query(F.data == "filters:menu")
async def show_filters(callback: CallbackQuery, current_user: User) -> None:
    await render(callback, current_user)


@router.callback_query(F.data == "filters:digits")
async def toggle_digits(callback: CallbackQuery, current_user: User) -> None:
    current_user.digits_enabled = not current_user.digits_enabled
    current_user.style_mode = "mixed" if current_user.digits_enabled else "clean"
    await render(callback, current_user, "Цифры обновлены")


@router.callback_query(F.data == "filters:underscore")
async def toggle_underscore(callback: CallbackQuery, current_user: User) -> None:
    current_user.underscore_enabled = not current_user.underscore_enabled
    await render(callback, current_user, "Подчёркивание обновлено")
