from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import add_search
from keyboards import search as kb
from services.attempts import attempts_reset_left, can_search, consume_attempt
from services.prime_access import is_prime_active
from services.reservations import is_username_reserved, reserve_username
from services.username_checker import UsernameCheckError, UsernameCheckerAdapter, is_username_available
from services.username_generator import generate_username
from texts import (
    CHECK_UNAVAILABLE,
    GENERATING,
    NOT_FOUND,
    PRIME_LOCKED,
    SEARCH_MENU,
    attempts_limit,
    reserve_already_own,
    reserve_limit_reached,
    reserve_success,
    reserve_taken,
    username_found,
)
from utils.validators import is_valid_username, normalize_username

logger = logging.getLogger(__name__)
router = Router(name="search")


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


@router.callback_query(F.data == "search:menu")
async def search_menu(callback: CallbackQuery) -> None:
    await safe_edit(callback, SEARCH_MENU, reply_markup=kb.search_menu())
    await callback.answer()


@router.callback_query(F.data.startswith("search:length:"))
async def search_by_length(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
    username_checker: UsernameCheckerAdapter,
    redis: Redis,
) -> None:
    length = int(callback.data.split(":")[-1])

    if length == 5 and not is_prime_active(current_user):
        await safe_edit(callback, PRIME_LOCKED, reply_markup=kb.prime_locked())
        await callback.answer()
        return

    if not can_search(current_user, settings):
        await safe_edit(
            callback,
            attempts_limit(attempts_reset_left(current_user, settings)),
            reply_markup=kb.prime_locked(),
        )
        await callback.answer()
        return

    await safe_edit(callback, GENERATING)
    await callback.answer()

    filters = {
        "digits_enabled": current_user.digits_enabled,
        "underscore_enabled": current_user.underscore_enabled,
        "style_mode": current_user.style_mode,
        "reserved_excluded": True,
    }
    max_candidates = settings.PRIME_SEARCH_MAX_CANDIDATES if is_prime_active(current_user) else settings.SEARCH_MAX_CANDIDATES

    try:
        for _ in range(max_candidates):
            candidate = generate_username(
                length,
                current_user.digits_enabled,
                current_user.underscore_enabled,
                current_user.style_mode,
            )
            if await is_username_reserved(session, candidate):
                continue
            if await is_username_available(candidate, checker=username_checker, redis=redis):
                consume_attempt(current_user, settings)
                await add_search(session, current_user, candidate, length, filters, "found")
                await safe_edit(callback, username_found(candidate), reply_markup=kb.result(candidate, length))
                return
    except UsernameCheckError:
        logger.warning("username checker temporarily unavailable")
        await add_search(session, current_user, None, length, filters, "checker_error")
        await safe_edit(callback, CHECK_UNAVAILABLE, reply_markup=kb.retry(length))
        return

    consume_attempt(current_user, settings)
    await add_search(session, current_user, None, length, filters, "not_found")
    await safe_edit(callback, NOT_FOUND, reply_markup=kb.retry(length))


@router.callback_query(F.data.startswith("search:reserve:"))
async def reserve_found_username(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Не могу прочитать ник", show_alert=True)
        return

    username = normalize_username(parts[2])
    try:
        length = int(parts[3])
    except ValueError:
        length = len(username)

    if not is_valid_username(username):
        await callback.answer("Некорректный username", show_alert=True)
        return

    result = await reserve_username(session, current_user, username, settings)

    if result.status == "reserved":
        await safe_edit(
            callback,
            reserve_success(username, result.used, result.limit),
            reply_markup=kb.reserved_result(username, length),
        )
        await callback.answer("Ник закреплён")
        return

    if result.status == "already_own":
        await safe_edit(
            callback,
            reserve_already_own(username, result.used, result.limit),
            reply_markup=kb.reserved_result(username, length),
        )
        await callback.answer("Уже в твоём резерве")
        return

    if result.status == "limit":
        await safe_edit(callback, reserve_limit_reached(result.limit), reply_markup=kb.reserve_error(length))
        await callback.answer("Лимит резервов", show_alert=True)
        return

    await safe_edit(callback, reserve_taken(username), reply_markup=kb.reserve_error(length))
    await callback.answer("Уже занято", show_alert=True)
