from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import add_search
from keyboards import search as kb
from services.attempts import attempts_reset_left, can_search, consume_attempt
from services.prime_access import is_prime_active
from services.username_checker import UsernameCheckError, UsernameCheckerAdapter, is_username_available
from services.username_generator import generate_username
from texts import CHECK_UNAVAILABLE, GENERATING, NOT_FOUND, PRIME_LOCKED, SEARCH_MENU, attempts_limit, username_found

logger = logging.getLogger(__name__)
router = Router(name="search")


@router.callback_query(F.data == "search:menu")
async def search_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(SEARCH_MENU, reply_markup=kb.search_menu())
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
        await callback.message.edit_text(PRIME_LOCKED, reply_markup=kb.prime_locked())
        await callback.answer()
        return

    if not can_search(current_user, settings):
        await callback.message.edit_text(
            attempts_limit(attempts_reset_left(current_user, settings)),
            reply_markup=kb.prime_locked(),
        )
        await callback.answer()
        return

    await callback.message.edit_text(GENERATING)
    await callback.answer()

    filters = {
        "digits_enabled": current_user.digits_enabled,
        "underscore_enabled": current_user.underscore_enabled,
        "style_mode": current_user.style_mode,
    }
    max_candidates = settings.PRIME_SEARCH_MAX_CANDIDATES if is_prime_active(current_user) else settings.SEARCH_MAX_CANDIDATES

    try:
        for _ in range(max_candidates):
            candidate = generate_username(length, current_user.digits_enabled, current_user.underscore_enabled, current_user.style_mode)
            if await is_username_available(candidate, checker=username_checker, redis=redis):
                consume_attempt(current_user, settings)
                await add_search(session, current_user, candidate, length, filters, "found")
                await callback.message.edit_text(username_found(candidate), reply_markup=kb.result(candidate, length))
                return
    except UsernameCheckError:
        logger.warning("username checker temporarily unavailable")
        await add_search(session, current_user, None, length, filters, "checker_error")
        await callback.message.edit_text(CHECK_UNAVAILABLE, reply_markup=kb.retry(length))
        return

    consume_attempt(current_user, settings)
    await add_search(session, current_user, None, length, filters, "not_found")
    await callback.message.edit_text(NOT_FOUND, reply_markup=kb.retry(length))
