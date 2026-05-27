from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from keyboards.profile import profile_menu, reservations_menu
from services.attempts import attempts_reset_left, total_attempts
from services.prime_access import is_prime_active
from services.reservations import (
    count_active_reservations,
    get_user_reservation_by_id,
    release_reservation,
    reservation_limit,
    user_active_reservations,
)
from texts import profile, reservation_released, reservations_list_text

router = Router(name="profile")


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(F.data == "profile:open")
async def open_profile(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    is_prime_active(current_user)
    link = f"https://t.me/{settings.BOT_USERNAME}?start={current_user.telegram_id}"
    reserved_count = await count_active_reservations(session, current_user)
    reserved_limit = reservation_limit(current_user, settings)
    await safe_edit(
        callback,
        profile(
            current_user,
            settings,
            attempts_reset_left(current_user, settings),
            total_attempts(current_user, settings),
            reserved_count,
            reserved_limit,
        ),
        reply_markup=profile_menu(link),
    )
    await callback.answer()


@router.callback_query(F.data == "profile:reservations")
async def open_reservations(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    reservations = await user_active_reservations(session, current_user)
    limit = reservation_limit(current_user, settings)
    await safe_edit(
        callback,
        reservations_list_text(reservations, len(reservations), limit),
        reply_markup=reservations_menu(reservations),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("profile:reservation:release:"))
async def release_reserved_username(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
) -> None:
    try:
        reservation_id = int(callback.data.split(":")[-1])
    except ValueError:
        await callback.answer("Не могу прочитать резерв", show_alert=True)
        return

    reservation = await get_user_reservation_by_id(session, current_user, reservation_id)
    if not reservation:
        await callback.answer("Резерв не найден", show_alert=True)
        return

    username = reservation.username
    await release_reservation(session, reservation)
    await safe_edit(callback, reservation_released(username), reply_markup=reservations_menu([]))
    await callback.answer("Резерв снят")
