from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database.models import User
from keyboards.filters import filters_menu as filters_kb
from keyboards.main import back_home
from texts import FILTERS_SAVED, filters_menu

router = Router(name="filters")


async def render(callback: CallbackQuery, user: User) -> None:
    await callback.message.edit_text(filters_menu(user), reply_markup=filters_kb(user.digits_enabled, user.underscore_enabled))
    await callback.answer()


@router.callback_query(F.data == "filters:menu")
async def show_filters(callback: CallbackQuery, current_user: User) -> None:
    await render(callback, current_user)


@router.callback_query(F.data == "filters:digits")
async def toggle_digits(callback: CallbackQuery, current_user: User) -> None:
    current_user.digits_enabled = not current_user.digits_enabled
    current_user.style_mode = "mixed" if current_user.digits_enabled else current_user.style_mode
    await render(callback, current_user)


@router.callback_query(F.data == "filters:underscore")
async def toggle_underscore(callback: CallbackQuery, current_user: User) -> None:
    current_user.underscore_enabled = not current_user.underscore_enabled
    await render(callback, current_user)


@router.callback_query(F.data == "filters:letters")
async def letters_only(callback: CallbackQuery, current_user: User) -> None:
    current_user.digits_enabled = False
    current_user.underscore_enabled = False
    current_user.style_mode = "clean"
    await render(callback, current_user)


@router.callback_query(F.data == "filters:mixed")
async def mixed(callback: CallbackQuery, current_user: User) -> None:
    current_user.digits_enabled = True
    current_user.style_mode = "mixed"
    await render(callback, current_user)


@router.callback_query(F.data == "filters:save")
async def save_filters(callback: CallbackQuery) -> None:
    await callback.message.edit_text(FILTERS_SAVED, reply_markup=back_home())
    await callback.answer()
