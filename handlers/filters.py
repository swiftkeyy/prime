from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.models import User
from keyboards.filters import filters_menu as filters_kb
from texts import filters_menu
from utils.telegram import safe_callback_answer, safe_edit_callback

router = Router(name="filters")


async def render(callback: CallbackQuery, user: User, notice: str | None = None) -> None:
    await safe_edit_callback(
        callback,
        filters_menu(user),
        reply_markup=filters_kb(user.digits_enabled, user.underscore_enabled, user.style_mode),
    )
    await safe_callback_answer(callback, notice)


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


@router.callback_query(F.data == "filters:style")
async def toggle_style(callback: CallbackQuery, current_user: User) -> None:
    styles = ["clean", "soft", "brand", "brutal", "techno", "mixed"]
    try:
        current_index = styles.index(current_user.style_mode)
    except ValueError:
        current_index = 0
    current_user.style_mode = styles[(current_index + 1) % len(styles)]
    current_user.digits_enabled = current_user.style_mode in {"mixed", "techno"}
    await render(callback, current_user, "Стиль обновлён")
