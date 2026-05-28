from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import add_search
from keyboards import search as kb
from keyboards.prime import prime_locked_cta
from services.attempts import attempts_reset_left, can_search, consume_attempt
from services.prime_access import is_prime_active
from services.reservations import is_username_reserved, reserve_username
from services.username_stock import take_available_username
from services.username_checker import (
    UsernameCheckError,
    UsernameCheckerAdapter,
    UsernameCheckerNotConfigured,
    UsernameCheckerRateLimited,
    is_username_available,
)
from services.username_generator import generate_username, generate_username_variants, normalize_username_seed
from texts import (
    CHECK_UNAVAILABLE,
    CUSTOM_SEARCH_LOCKED,
    CUSTOM_NICK_BAD_INPUT,
    CUSTOM_NICK_GENERATING,
    CUSTOM_NICK_PROMPT,
    GENERATING,
    generating_for_length,
    NOT_FOUND,
    PRIME_LOCKED,
    SEARCH_MENU,
    STOCK_EMPTY,
    attempts_limit,
    custom_nick_not_found,
    custom_nick_results,
    check_rate_limited,
    reserve_already_own,
    reserve_limit_reached,
    reserve_success,
    reserve_taken,
    username_found,
)
from utils.telegram import safe_callback_answer, safe_edit_callback, safe_edit_message
from utils.validators import is_valid_username, normalize_username

logger = logging.getLogger(__name__)
router = Router(name="search")


class CustomNickState(StatesGroup):
    waiting_seed = State()
async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    await safe_edit_callback(callback, text, reply_markup=reply_markup)


async def safe_message_edit(message: Message, text: str, reply_markup=None) -> None:
    await safe_edit_message(message, text, reply_markup=reply_markup)


@router.callback_query(F.data == "search:menu")
async def search_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_callback_answer(callback)
    await state.clear()
    await safe_edit(callback, SEARCH_MENU, reply_markup=kb.search_menu())


@router.callback_query(F.data == "search:custom:start")
async def custom_nick_start(callback: CallbackQuery, state: FSMContext, current_user: User) -> None:
    if not is_prime_active(current_user):
        await safe_callback_answer(callback)
        await safe_edit(callback, CUSTOM_SEARCH_LOCKED, reply_markup=prime_locked_cta())
        return
    await safe_callback_answer(callback)
    await state.set_state(CustomNickState.waiting_seed)
    await safe_edit(callback, CUSTOM_NICK_PROMPT, reply_markup=kb.custom_prompt())


@router.message(CustomNickState.waiting_seed, F.text, ~F.text.startswith("/"))
async def custom_nick_process(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
    username_checker: UsernameCheckerAdapter,
    redis: Redis,
) -> None:
    seed = normalize_username_seed(message.text or "")
    if not seed:
        await message.answer(CUSTOM_NICK_BAD_INPUT, reply_markup=kb.custom_prompt())
        return

    if not can_search(current_user, settings):
        await state.clear()
        await message.answer(
            attempts_limit(attempts_reset_left(current_user, settings)),
            reply_markup=kb.prime_locked(),
        )
        return

    status_message = await message.answer(CUSTOM_NICK_GENERATING)

    filters = {
        "mode": "custom_suggestions",
        "seed": seed,
        "digits_enabled": current_user.digits_enabled,
        "underscore_enabled": current_user.underscore_enabled,
        "style_mode": current_user.style_mode,
        "reserved_excluded": True,
    }
    configured_max_candidates = (
        settings.PRIME_USERNAME_SUGGESTIONS_MAX_CANDIDATES
        if is_prime_active(current_user)
        else settings.USERNAME_SUGGESTIONS_MAX_CANDIDATES
    )
    # Hard cap: webhook handlers must finish fast. One custom request checks
    # several real Telegram usernames, so do not let env values make it hang.
    max_candidates = min(configured_max_candidates, 12 if is_prime_active(current_user) else 6)
    target_count = max(1, settings.USERNAME_SUGGESTIONS_COUNT)
    candidates = generate_username_variants(seed, limit=max_candidates)
    found: list[str] = []

    custom_timeout = max(8, settings.SEARCH_TOTAL_TIMEOUT_SECONDS)
    if is_prime_active(current_user):
        max_candidates = min(max_candidates, 10)
        custom_timeout = min(custom_timeout, 14)
    deadline = asyncio.get_event_loop().time() + custom_timeout

    for candidate in candidates:
        if len(found) >= target_count:
            break
        time_left = deadline - asyncio.get_event_loop().time()
        if time_left <= 1:
            logger.info("custom username suggestions deadline reached seed=%s max_candidates=%s", seed, max_candidates)
            break
        if await is_username_reserved(session, candidate):
            continue
        try:
            available = await asyncio.wait_for(
                is_username_available(candidate, checker=username_checker, redis=redis),
                timeout=min(max(3, settings.USERNAME_CHECK_TIMEOUT + 2), max(1, time_left)),
            )
        except UsernameCheckerRateLimited as exc:
            logger.warning("username checker rate-limited for custom suggestions retry_after=%s", exc.retry_after)
            await add_search(session, current_user, None, len(seed), filters, "checker_rate_limited")
            await state.clear()
            await safe_message_edit(status_message, check_rate_limited(exc.retry_after), reply_markup=kb.custom_prompt())
            return
        except UsernameCheckerNotConfigured:
            logger.warning("username checker is not configured for custom suggestions")
            await add_search(session, current_user, None, len(seed), filters, "checker_error")
            await state.clear()
            await safe_message_edit(status_message, CHECK_UNAVAILABLE, reply_markup=kb.custom_prompt())
            return
        except (UsernameCheckError, asyncio.TimeoutError) as exc:
            logger.warning("skip custom candidate @%s after checker error: %s", candidate, exc.__class__.__name__)
            continue
        if available:
            found.append(candidate)

    consume_attempt(current_user, settings)
    await add_search(session, current_user, found[0] if found else None, len(seed), filters, "custom_found" if found else "custom_not_found")
    await state.clear()

    if found:
        await safe_message_edit(status_message, custom_nick_results(seed, found), reply_markup=kb.custom_results(found))
        return

    await safe_message_edit(status_message, custom_nick_not_found(seed), reply_markup=kb.custom_prompt())


@router.callback_query(F.data.startswith("search:length:"))
async def search_by_length(
    callback: CallbackQuery,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
    username_checker: UsernameCheckerAdapter,
    redis: Redis,
) -> None:
    await safe_callback_answer(callback)
    length = int(callback.data.split(":")[-1])

    if length == 5 and not is_prime_active(current_user):
        await safe_edit(callback, PRIME_LOCKED, reply_markup=kb.prime_locked())
        return

    if not can_search(current_user, settings):
        await safe_edit(
            callback,
            attempts_limit(attempts_reset_left(current_user, settings)),
            reply_markup=kb.prime_locked(),
        )
        return

    filters = {
        "mode": "beautiful_words",
        "digits_enabled": current_user.digits_enabled,
        "underscore_enabled": current_user.underscore_enabled,
        "style_mode": current_user.style_mode,
        "reserved_excluded": True,
    }
    prime_active = is_prime_active(current_user)
    search_digits_enabled = current_user.digits_enabled
    search_style_mode = current_user.style_mode
    configured_max_candidates = settings.PRIME_SEARCH_MAX_CANDIDATES if prime_active else settings.SEARCH_MAX_CANDIDATES
    if length == 5 and prime_active:
        # Short clean usernames are extremely scarce. Use a deeper scan only for PRIME 5-symbol mode.
        max_candidates = min(max(settings.PRIME_5_SEARCH_MAX_CANDIDATES, configured_max_candidates), 8)
        total_timeout = max(12, settings.PRIME_5_SEARCH_TOTAL_TIMEOUT_SECONDS)
    else:
        max_candidates = min(configured_max_candidates, 7 if prime_active else 4)
        total_timeout = max(8, settings.SEARCH_TOTAL_TIMEOUT_SECONDS)

    await safe_edit(callback, generating_for_length(length, max_candidates))

    if settings.USERNAME_STOCK_ENABLED:
        stock = await take_available_username(
            session,
            current_user,
            length,
            settings=settings,
            digits_enabled=search_digits_enabled,
            underscore_enabled=current_user.underscore_enabled,
        )

        # Filters are strict: if digits are OFF, stock items with digits are not issued.

        if stock.username:
            consume_attempt(current_user, settings)
            await add_search(session, current_user, stock.username, length, filters | {"source": "stock"}, "found")
            await safe_edit(callback, username_found(stock.username), reply_markup=kb.result(stock.username, length))
            return

        if not settings.USERNAME_LIVE_CHECK_ENABLED:
            await add_search(session, current_user, None, length, filters | {"source": "stock"}, "stock_empty")
            await safe_edit(callback, STOCK_EMPTY, reply_markup=kb.retry(length))
            return

    deadline = asyncio.get_event_loop().time() + total_timeout

    for _ in range(max_candidates):
        time_left = deadline - asyncio.get_event_loop().time()
        if time_left <= 1:
            logger.info("username search deadline reached length=%s max_candidates=%s", length, max_candidates)
            break
        candidate = generate_username(
            length,
            search_digits_enabled,
            current_user.underscore_enabled,
            search_style_mode,
        )
        if await is_username_reserved(session, candidate):
            continue
        try:
            available = await asyncio.wait_for(
                is_username_available(candidate, checker=username_checker, redis=redis),
                timeout=min(max(3, settings.USERNAME_CHECK_TIMEOUT + 2), max(1, time_left)),
            )
        except UsernameCheckerRateLimited as exc:
            logger.warning("username checker rate-limited retry_after=%s", exc.retry_after)
            await add_search(session, current_user, None, length, filters, "checker_rate_limited")
            await safe_edit(callback, check_rate_limited(exc.retry_after), reply_markup=kb.retry(length))
            return
        except UsernameCheckerNotConfigured:
            logger.warning("username checker is not configured")
            await add_search(session, current_user, None, length, filters, "checker_error")
            await safe_edit(callback, CHECK_UNAVAILABLE, reply_markup=kb.retry(length))
            return
        except (UsernameCheckError, asyncio.TimeoutError) as exc:
            logger.warning("skip candidate @%s after checker error: %s", candidate, exc.__class__.__name__)
            continue
        if available:
            consume_attempt(current_user, settings)
            await add_search(session, current_user, candidate, length, filters, "found")
            await safe_edit(callback, username_found(candidate), reply_markup=kb.result(candidate, length))
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
        await safe_callback_answer(callback, "Не могу прочитать ник", show_alert=True)
        return

    username = normalize_username(parts[2])
    try:
        length = int(parts[3])
    except ValueError:
        length = len(username)

    if not is_valid_username(username):
        await safe_callback_answer(callback, "Некорректный username", show_alert=True)
        return

    result = await reserve_username(session, current_user, username, settings)

    if result.status == "reserved":
        await safe_edit(
            callback,
            reserve_success(username, result.used, result.limit),
            reply_markup=kb.reserved_result(username, length),
        )
        await safe_callback_answer(callback, "Ник закреплён")
        return

    if result.status == "already_own":
        await safe_edit(
            callback,
            reserve_already_own(username, result.used, result.limit),
            reply_markup=kb.reserved_result(username, length),
        )
        await safe_callback_answer(callback, "Уже в твоём резерве")
        return

    if result.status == "limit":
        await safe_edit(callback, reserve_limit_reached(result.limit), reply_markup=kb.reserve_error(length))
        await safe_callback_answer(callback, "Лимит резервов", show_alert=True)
        return

    await safe_edit(callback, reserve_taken(username), reply_markup=kb.reserve_error(length))
    await safe_callback_answer(callback, "Уже занято", show_alert=True)
