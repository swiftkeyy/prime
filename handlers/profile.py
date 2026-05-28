from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import best_user_searches
from keyboards.profile import profile_menu, reservations_menu
from services.attempts import attempts_reset_left, total_attempts
from services.prime_access import is_prime_active
from utils.referrals import make_referral_link
from services.reservations import (
    count_active_reservations,
    get_user_reservation_by_id,
    release_reservation,
    reservation_limit,
    user_active_reservations,
)
from texts import best_searches_text, profile, reservation_released, reservations_list_text
from utils.telegram import safe_callback_answer, safe_edit_callback

router = Router(name="profile")


@router.callback_query(F.data == "profile:open")
async def open_profile(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    is_prime_active(current_user)
    me = await bot.get_me()
    bot_username = me.username or settings.BOT_USERNAME
    link = make_referral_link(bot_username, current_user)
    reserved_count = await count_active_reservations(session, current_user)
    reserved_limit = reservation_limit(current_user, settings)
    await safe_edit_callback(
        callback,
        profile(
            current_user,
            settings,
            attempts_reset_left(current_user, settings),
            total_attempts(current_user, settings),
            reserved_count,
            reserved_limit,
            bot_username,
        ),
        reply_markup=profile_menu(link),
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "profile:reservations")
async def open_reservations(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    reservations = await user_active_reservations(session, current_user)
    limit = reservation_limit(current_user, settings)
    await safe_edit_callback(
        callback,
        reservations_list_text(reservations, len(reservations), limit),
        reply_markup=reservations_menu(reservations),
    )
    await safe_callback_answer(callback)


@router.callback_query(F.data == "profile:best")
async def open_best_searches(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    searches = await best_user_searches(session, current_user)
    me = await bot.get_me()
    bot_username = me.username or settings.BOT_USERNAME
    link = make_referral_link(bot_username, current_user)
    await safe_edit_callback(callback, best_searches_text(searches), reply_markup=profile_menu(link))
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("profile:reservation:release:"))
async def release_reserved_username(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
) -> None:
    try:
        reservation_id = int(callback.data.split(":")[-1])
    except ValueError:
        await safe_callback_answer(callback, "Не могу прочитать резерв", show_alert=True)
        return

    reservation = await get_user_reservation_by_id(session, current_user, reservation_id)
    if not reservation:
        await safe_callback_answer(callback, "Резерв не найден", show_alert=True)
        return

    username = reservation.username
    await release_reservation(session, reservation)
    await safe_edit_callback(callback, reservation_released(username), reply_markup=reservations_menu([]))
    await safe_callback_answer(callback, "Резерв снят")
