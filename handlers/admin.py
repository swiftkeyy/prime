from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from redis.asyncio import Redis
from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from config import Settings
from database.models import User
from database.queries import (
    admin_dashboard,
    admin_deactivate_promo,
    admin_promos_page,
    admin_recent_payments,
    admin_recent_searches,
    admin_settings_list,
    admin_target_user_ids,
    admin_upsert_setting,
    admin_user_payments,
    admin_user_searches,
    admin_users_page,
    create_promo_code,
    get_user_by_id_or_username,
)
from keyboards.admin import (
    ADMIN_MODES,
    BROADCAST_AUDIENCES,
    PAYMENT_FILTERS,
    admin_back,
    admin_close_back,
    admin_menu,
    broadcast_audience_kb,
    broadcast_confirm,
    payments_menu,
    prime_control_kb,
    promo_list_kb,
    promo_menu,
    searches_kb,
    settings_kb,
    user_card_kb,
    users_menu,
    users_page_kb,
)
from services.prime_access import grant_prime, revoke_prime
from utils.formatters import h, money_rub, tariff_title
from utils.time import format_dt, utcnow
from utils.validators import normalize_promo

router = Router(name="admin")
logger = logging.getLogger("prime_nick.admin")


class AdminStates(StatesGroup):
    waiting_user = State()
    waiting_give_prime = State()
    waiting_remove_prime = State()
    waiting_promo = State()
    waiting_promo_disable = State()
    waiting_broadcast = State()
    preview_broadcast = State()
    waiting_setting = State()


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_id_set


async def deny(message_or_callback: Message | CallbackQuery, settings: Settings) -> bool:
    user = message_or_callback.from_user
    if not user or not is_admin(user.id, settings):
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer("Нет доступа", show_alert=True)
        else:
            await message_or_callback.answer("⛔ Нет доступа")
        return True
    return False


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None, answer: str | None = None) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise
    await callback.answer(answer)


def admin_home_text() -> str:
    return """⚙️ <b>PRIME ADMIN</b>

╭─ <b>Command Core</b>
│ Управление PRIME NICK в один клик.
│ Пользователи, PRIME PASS, платежи,
│ промокоды, рассылки и runtime-контроль.
╰ Выбери модуль ниже."""


def user_status(user: User) -> str:
    active = user.is_prime and user.prime_until and user.prime_until >= utcnow()
    return "💠 PRIME PASS" if active else "🛡 Base"


def user_card_text(user: User) -> str:
    invited_by = f"<code>{user.invited_by}</code>" if user.invited_by else "—"
    return f"""👤 <b>PRIME USER CARD</b>

╭─ <b>Identity</b>
│ TG ID: <code>{user.telegram_id}</code>
│ DB ID: <code>{user.id}</code>
│ Username: @{h(user.username or '—')}
│ Имя: {h(user.first_name or '—')}
╰ Статус: <b>{user_status(user)}</b>

╭─ <b>Access</b>
│ PRIME до: <b>{format_dt(user.prime_until) if user.is_prime else 'не активен'}</b>
│ Free attempts: <b>{user.attempts_left}</b>
│ Bonus attempts: <b>{user.bonus_attempts}</b>
╰ Last reset: <b>{format_dt(user.last_attempts_reset)}</b>

╭─ <b>Activity</b>
│ Поисков: <b>{user.total_searches}</b>
│ Рефералов: <b>{user.referrals_count}</b>
│ Invited by: {invited_by}
╰ Создан: <b>{format_dt(user.created_at)}</b>

╭─ <b>Filters</b>
│ Цифры: <b>{'ON' if user.digits_enabled else 'OFF'}</b>
│ Underscore: <b>{'ON' if user.underscore_enabled else 'OFF'}</b>
╰ Style: <b>{h(user.style_mode)}</b>"""


def format_payment_amount(amount: Any, currency: str) -> str:
    if currency == "RUB":
        return money_rub(amount)
    if currency == "XTR":
        return f"{int(amount)} ⭐"
    return f"{amount} {currency}"


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    if await deny(message, settings):
        return
    await message.answer(admin_home_text(), reply_markup=admin_menu())


@router.callback_query(F.data == "admin:menu")
async def admin_home(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await safe_edit(callback, admin_home_text(), admin_menu())


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    s = await admin_dashboard(session)
    conversion = 0.0 if not s["users_total"] else (s["prime_active"] / s["users_total"]) * 100
    found_rate = 0.0 if not s["searches_total"] else (s["found_total"] / s["searches_total"]) * 100
    text = f"""📊 <b>PRIME NICK · COMMAND CENTER</b>

╭─ <b>Users</b>
│ Всего: <b>{s['users_total']}</b>
│ Сегодня: <b>+{s['users_today']}</b>
│ 7 дней: <b>+{s['users_week']}</b>
│ PRIME active: <b>{s['prime_active']}</b>
│ Base: <b>{s['base_users']}</b>
╰ PRIME CR: <b>{conversion:.1f}%</b>

╭─ <b>Search</b>
│ Всего: <b>{s['searches_total']}</b>
│ Сегодня: <b>{s['searches_today']}</b>
│ 7 дней: <b>{s['searches_week']}</b>
│ Найдено: <b>{s['found_total']}</b>
╰ Hit-rate: <b>{found_rate:.1f}%</b>

╭─ <b>Money</b>
│ Paid invoices: <b>{s['payments_paid']}</b>
│ Pending: <b>{s['payments_pending']}</b>
│ RUB: <b>{money_rub(s['rub_revenue'])}</b>
╰ Stars: <b>{int(s['stars_revenue'])} ⭐</b>

╭─ <b>Growth</b>
│ Рефералы: <b>{s['referrals_total']}</b>
│ Активные промо: <b>{s['active_promos']}</b>
│ Активации промо: <b>{s['promo_activations']}</b>
╰ Expired PRIME flag: <b>{s['prime_expired_flagged']}</b>"""
    await safe_edit(callback, text, admin_close_back())


@router.callback_query(F.data == "admin:health")
async def admin_health(
    callback: CallbackQuery,
    session: AsyncSession,
    redis: Redis,
    bot: Bot,
    engine: AsyncEngine,
    settings: Settings,
) -> None:
    if await deny(callback, settings):
        return

    db_ok = redis_ok = webhook_ok = False
    webhook_url = "—"
    pending = "—"
    pool_status = "—"
    try:
        await session.execute(sql_text("select 1"))
        db_ok = True
        pool_status = engine.sync_engine.pool.status()
    except Exception as exc:  # noqa: BLE001
        pool_status = exc.__class__.__name__
    try:
        redis_ok = bool(await redis.ping())
    except Exception:  # noqa: BLE001
        redis_ok = False
    try:
        info = await bot.get_webhook_info()
        webhook_url = info.url or "—"
        pending = str(info.pending_update_count)
        webhook_ok = webhook_url == settings.webhook_url
    except Exception:  # noqa: BLE001
        webhook_ok = False

    text = f"""🩺 <b>PRIME HEALTH</b>

╭─ <b>Runtime</b>
│ DB: <b>{'✅ OK' if db_ok else '⛔ FAIL'}</b>
│ Redis: <b>{'✅ OK' if redis_ok else '⛔ FAIL'}</b>
│ Webhook: <b>{'✅ OK' if webhook_ok else '⛔ CHECK'}</b>
╰ Pending updates: <b>{pending}</b>

╭─ <b>Webhook</b>
│ Current:
│ <code>{h(webhook_url)}</code>
│ Expected:
│ <code>{h(settings.webhook_url)}</code>
╰ Mode: <b>{settings.USERNAME_CHECK_MODE}</b>

╭─ <b>Pool</b>
╰ <code>{h(pool_status)}</code>"""
    await safe_edit(callback, text, admin_close_back())


@router.callback_query(F.data == "admin:users")
async def admin_users(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await safe_edit(
        callback,
        "👥 <b>PRIME USERS</b>\n\nВыбери сегмент. Каждая карточка открывается в один клик.",
        users_menu(),
    )


@router.callback_query(F.data.regexp(r"^admin:users:(latest|prime|top_searches|top_refs):(\d+)$"))
async def admin_users_page_view(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    _, _, mode, page_raw = callback.data.split(":")
    page = int(page_raw)
    users, total = await admin_users_page(session, mode=mode, page=page)
    title = ADMIN_MODES.get(mode, mode)
    if not users:
        await safe_edit(callback, f"👥 <b>{title}</b>\n\nПользователей в сегменте нет.", users_menu())
        return
    text = f"👥 <b>{title}</b> · страница {page + 1}\n\nВсего в сегменте: <b>{total}</b>\nОткрой пользователя кнопкой ниже."
    await safe_edit(callback, text, users_page_kb(users, mode, page, total))


@router.callback_query(F.data.regexp(r"^admin:usercard:\d+$"))
async def admin_user_card(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    telegram_id = callback.data.split(":")[-1]
    user = await get_user_by_id_or_username(session, telegram_id)
    if not user:
        await safe_edit(callback, "⛔ Пользователь не найден", admin_back())
        return
    await safe_edit(callback, user_card_text(user), user_card_kb(user.telegram_id))


@router.callback_query(F.data == "admin:user")
async def ask_user(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_user)
    await safe_edit(callback, "🔎 <b>Поиск пользователя</b>\n\nОтправь telegram_id или @username.", admin_back())


@router.message(AdminStates.waiting_user)
async def show_user(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    user = await get_user_by_id_or_username(session, message.text or "")
    await state.clear()
    if not user:
        await message.answer("⛔ Пользователь не найден", reply_markup=admin_back())
        return
    await message.answer(user_card_text(user), reply_markup=user_card_kb(user.telegram_id))


@router.callback_query(F.data == "admin:prime_control")
async def prime_control(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await safe_edit(
        callback,
        "💠 <b>PRIME CONTROL</b>\n\nБыстрая ручная выдача, снятие и список активных PRIME PASS.",
        prime_control_kb(),
    )


@router.callback_query(F.data == "admin:give_prime")
async def ask_give_prime(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_give_prime)
    await safe_edit(
        callback,
        "💠 <b>Выдать PRIME PASS</b>\n\nОтправь: <code>telegram_id срок</code>\n\nСрок: <code>1d</code>, <code>7d</code>, <code>30d</code>, <code>forever</code>",
        admin_back(),
    )


@router.message(AdminStates.waiting_give_prime)
async def give_prime(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or parts[1] not in {"1d", "7d", "30d", "forever"}:
        await message.answer("⛔ Формат: <code>telegram_id 7d</code>", reply_markup=admin_back())
        return
    user = await get_user_by_id_or_username(session, parts[0])
    if not user:
        await message.answer("⛔ Пользователь не найден", reply_markup=admin_back())
        return
    grant_prime(user, tariff=parts[1])
    await state.clear()
    await message.answer(
        f"✅ PRIME PASS выдан: <code>{user.telegram_id}</code> · {tariff_title(parts[1])}",
        reply_markup=user_card_kb(user.telegram_id),
    )


@router.callback_query(F.data.regexp(r"^admin:userprime:\d+:(1d|7d|30d|forever|revoke)$"))
async def user_prime_action(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    _, _, tg_raw, action = callback.data.split(":")
    user = await get_user_by_id_or_username(session, tg_raw)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    if action == "revoke":
        revoke_prime(user)
        notice = "PRIME отключён"
    else:
        grant_prime(user, tariff=action)
        notice = f"PRIME + {tariff_title(action)}"
    await safe_edit(callback, user_card_text(user), user_card_kb(user.telegram_id), notice)


@router.callback_query(F.data == "admin:remove_prime")
async def ask_remove_prime(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_remove_prime)
    await safe_edit(callback, "⛔ Отправь telegram_id пользователя, у которого нужно забрать PRIME PASS.", admin_back())


@router.message(AdminStates.waiting_remove_prime)
async def remove_prime(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    user = await get_user_by_id_or_username(session, message.text or "")
    await state.clear()
    if not user:
        await message.answer("⛔ Пользователь не найден", reply_markup=admin_back())
        return
    revoke_prime(user)
    await message.answer(f"✅ PRIME PASS отключён: <code>{user.telegram_id}</code>", reply_markup=user_card_kb(user.telegram_id))


@router.callback_query(F.data.regexp(r"^admin:userattempts:\d+:(add5|add20|reset|zero)$"))
async def user_attempts_action(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    _, _, tg_raw, action = callback.data.split(":")
    user = await get_user_by_id_or_username(session, tg_raw)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    if action == "add5":
        user.bonus_attempts += 5
        notice = "+5 bonus attempts"
    elif action == "add20":
        user.bonus_attempts += 20
        notice = "+20 bonus attempts"
    elif action == "reset":
        user.attempts_left = settings.FREE_ATTEMPTS
        user.last_attempts_reset = utcnow()
        notice = "free attempts reset"
    else:
        user.attempts_left = 0
        user.bonus_attempts = 0
        notice = "attempts zeroed"
    await safe_edit(callback, user_card_text(user), user_card_kb(user.telegram_id), notice)


@router.callback_query(F.data.regexp(r"^admin:usersearches:\d+$"))
async def user_searches(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    tg_raw = callback.data.split(":")[-1]
    user = await get_user_by_id_or_username(session, tg_raw)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    items = await admin_user_searches(session, user, 10)
    lines = [f"🧬 <b>Поиски пользователя</b> · <code>{user.telegram_id}</code>"]
    if not items:
        lines.append("\nИстории пока нет.")
    for item in items:
        uname = f"@{h(item.username_result)}" if item.username_result else "—"
        lines.append(f"\n#{item.id} · {item.length} символов · <b>{h(item.status)}</b>\n{uname} · {format_dt(item.created_at)}")
    await safe_edit(callback, "\n".join(lines), user_card_kb(user.telegram_id))


@router.callback_query(F.data.regexp(r"^admin:userpayments:\d+$"))
async def user_payments(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    tg_raw = callback.data.split(":")[-1]
    user = await get_user_by_id_or_username(session, tg_raw)
    if not user:
        await callback.answer("Пользователь не найден", show_alert=True)
        return
    items = await admin_user_payments(session, user, 10)
    lines = [f"💳 <b>Платежи пользователя</b> · <code>{user.telegram_id}</code>"]
    if not items:
        lines.append("\nПлатежей пока нет.")
    for p in items:
        lines.append(
            f"\n#{p.id} · <b>{h(p.status)}</b> · {h(p.method)}\n"
            f"{format_payment_amount(p.amount, p.currency)} · {h(p.tariff)} · inv=<code>{h(p.invoice_id or '—')}</code>\n"
            f"{format_dt(p.created_at)}"
        )
    await safe_edit(callback, "\n".join(lines), user_card_kb(user.telegram_id))


@router.callback_query(F.data == "admin:promo")
async def promo_root(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await safe_edit(
        callback,
        "🎟 <b>PROMO CONTROL</b>\n\nСоздание, просмотр и отключение промокодов PRIME PASS.",
        promo_menu(),
    )


@router.callback_query(F.data == "admin:promo:create")
async def ask_promo(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_promo)
    await safe_edit(
        callback,
        "🎟 <b>Создать промокод</b>\n\nФормат:\n<code>CODE days max_uses YYYY-MM-DD</code>\n\nДата окончания необязательна:\n<code>PRIME7 7 100</code>",
        admin_back(),
    )


@router.message(AdminStates.waiting_promo)
async def create_promo(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    parts = (message.text or "").split()
    if len(parts) not in {3, 4}:
        await message.answer("⛔ Формат: <code>CODE days max_uses YYYY-MM-DD</code>", reply_markup=admin_back())
        return
    try:
        code = normalize_promo(parts[0])
        days = int(parts[1])
        max_uses = int(parts[2])
        expires_at = datetime.fromisoformat(parts[3]) if len(parts) == 4 else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if days <= 0 or max_uses <= 0:
            raise ValueError("days and max_uses must be positive")
    except Exception:  # noqa: BLE001
        await message.answer("⛔ Не удалось разобрать промокод", reply_markup=admin_back())
        return
    promo = await create_promo_code(session, code, days, max_uses, expires_at)
    await state.clear()
    await message.answer(
        f"✅ Промокод создан\n\nID: <code>{promo.id}</code>\nCode: <code>{promo.code}</code>\nPRIME: <b>{days} дней</b>\nЛимит: <b>{max_uses}</b>",
        reply_markup=promo_menu(),
    )


@router.callback_query(F.data == "admin:promo:list")
async def promo_list(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    promos = await admin_promos_page(session, active_only=True)
    lines = ["🎟 <b>Активные промокоды</b>"]
    if not promos:
        lines.append("\nАктивных промокодов нет.")
    for promo in promos:
        exp = format_dt(promo.expires_at) if promo.expires_at else "без срока"
        lines.append(
            f"\n#{promo.id} · <code>{h(promo.code)}</code>\n"
            f"PRIME: <b>{promo.prime_days} д.</b> · uses: <b>{promo.used_count}/{promo.max_uses}</b>\n"
            f"до: <b>{exp}</b>"
        )
    await safe_edit(callback, "\n".join(lines), promo_list_kb(promos))


@router.callback_query(F.data.regexp(r"^admin:promo:disable:\d+$"))
async def promo_disable_callback(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    promo_id = int(callback.data.split(":")[-1])
    promo = await admin_deactivate_promo(session, promo_id)
    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return
    await callback.answer(f"Промокод {promo.code} отключён", show_alert=True)
    promos = await admin_promos_page(session, active_only=True)
    await safe_edit(callback, "🎟 <b>Активные промокоды обновлены</b>", promo_list_kb(promos))


@router.callback_query(F.data == "admin:promo:disable_prompt")
async def promo_disable_prompt(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_promo_disable)
    await safe_edit(callback, "🧯 Отправь ID промокода, который нужно отключить.", admin_back())


@router.message(AdminStates.waiting_promo_disable)
async def promo_disable_message(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    if not (message.text or "").strip().isdigit():
        await message.answer("⛔ Нужен числовой ID промокода", reply_markup=admin_back())
        return
    promo = await admin_deactivate_promo(session, int(message.text.strip()))
    await state.clear()
    if not promo:
        await message.answer("⛔ Промокод не найден", reply_markup=admin_back())
        return
    await message.answer(f"✅ Промокод отключён: <code>{promo.code}</code>", reply_markup=promo_menu())


@router.callback_query(F.data == "admin:payments")
async def payments_root(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await safe_edit(callback, "💳 <b>PAYMENT RADAR</b>\n\nВыбери фильтр платежей.", payments_menu())


@router.callback_query(F.data.regexp(r"^admin:payments:(all|paid|created|pending|failed)$"))
async def payments_list(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    status = callback.data.split(":")[-1]
    items = await admin_recent_payments(session, status=status, limit=12)
    title = PAYMENT_FILTERS.get(status, status)
    lines = [f"💳 <b>Платежи · {title}</b>"]
    if not items:
        lines.append("\nПлатежей нет.")
    for p, tg_id in items:
        lines.append(
            f"\n#{p.id} · <code>{tg_id}</code> · <b>{h(p.status)}</b>\n"
            f"{format_payment_amount(p.amount, p.currency)} · {h(p.method)} · {h(p.tariff)}\n"
            f"inv=<code>{h(p.invoice_id or '—')}</code> · {format_dt(p.created_at)}"
        )
    await safe_edit(callback, "\n".join(lines), payments_menu())


@router.callback_query(F.data == "admin:searches")
async def searches_latest(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    items = await admin_recent_searches(session, 12)
    lines = ["🧬 <b>Последние поиски</b>"]
    if not items:
        lines.append("\nПоисков пока нет.")
    for item, tg_id in items:
        uname = f"@{h(item.username_result)}" if item.username_result else "—"
        lines.append(
            f"\n#{item.id} · <code>{tg_id}</code> · {item.length} chars · <b>{h(item.status)}</b>\n"
            f"{uname} · {format_dt(item.created_at)}"
        )
    await safe_edit(callback, "\n".join(lines), searches_kb())


@router.callback_query(F.data == "admin:broadcast")
async def ask_broadcast_audience(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.clear()
    await safe_edit(callback, "📢 <b>BROADCAST CORE</b>\n\nВыбери аудиторию рассылки.", broadcast_audience_kb())


@router.callback_query(F.data.regexp(r"^admin:broadcast:audience:(all|prime|base)$"))
async def ask_broadcast_text(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    audience = callback.data.split(":")[-1]
    await state.update_data(audience=audience)
    await state.set_state(AdminStates.waiting_broadcast)
    await safe_edit(
        callback,
        f"📢 <b>Рассылка</b>\n\nАудитория: <b>{BROADCAST_AUDIENCES[audience]}</b>\n\nОтправь текст. HTML-разметка поддерживается.",
        admin_back(),
    )


@router.message(AdminStates.waiting_broadcast)
async def preview_broadcast(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny(message, settings):
        return
    data = await state.get_data()
    audience = data.get("audience", "all")
    text = message.html_text or message.text or ""
    if not text.strip():
        await message.answer("⛔ Текст пустой", reply_markup=admin_back())
        return
    await state.update_data(text=text, audience=audience)
    await state.set_state(AdminStates.preview_broadcast)
    await message.answer(
        f"📢 <b>Предпросмотр</b>\nАудитория: <b>{BROADCAST_AUDIENCES.get(audience, audience)}</b>\n\n{text}",
        reply_markup=broadcast_confirm(audience),
    )


@router.callback_query(F.data == "admin:broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.clear()
    await safe_edit(callback, "❌ Рассылка отменена", admin_back())


@router.callback_query(F.data == "admin:broadcast:send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    data = await state.get_data()
    text = data.get("text")
    audience = data.get("audience", "all")
    if not text:
        await callback.answer("Текст не найден", show_alert=True)
        return
    ids = await admin_target_user_ids(session, audience=audience)
    sent = failed = blocked = 0
    await callback.message.edit_text(
        f"📢 <b>Рассылка запущена</b>\n\nАудитория: <b>{BROADCAST_AUDIENCES.get(audience, audience)}</b>\nПолучателей: <b>{len(ids)}</b>"
    )
    for index, chat_id in enumerate(ids, start=1):
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except TelegramForbiddenError:
            blocked += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("broadcast failed chat_id=%s error=%s", chat_id, exc.__class__.__name__)
        if index % 50 == 0:
            try:
                await callback.message.edit_text(
                    f"📢 <b>Рассылка идёт</b>\n\n{index}/{len(ids)}\n✅ {sent} · ⛔ {blocked} · ⚠️ {failed}"
                )
            except TelegramBadRequest:
                pass
        await asyncio.sleep(0.08)
    await state.clear()
    await callback.message.answer(
        f"✅ <b>Рассылка завершена</b>\n\nОтправлено: <b>{sent}</b>\nЗаблокировали бота: <b>{blocked}</b>\nОшибок: <b>{failed}</b>",
        reply_markup=admin_back(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:settings")
async def settings_root(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    text = f"""🧩 <b>RUNTIME CONTROL</b>

╭─ <b>Env snapshot</b>
│ Check mode: <b>{settings.USERNAME_CHECK_MODE}</b>
│ Search candidates: <b>{settings.SEARCH_MAX_CANDIDATES}</b>
│ PRIME candidates: <b>{settings.PRIME_SEARCH_MAX_CANDIDATES}</b>
│ Free attempts: <b>{settings.FREE_ATTEMPTS}</b>
╰ Cooldown: <b>{settings.ATTEMPTS_COOLDOWN_HOURS} ч.</b>

Таблица settings подходит для безопасных runtime-флагов, текстов, лимитов и внутренних переключателей."""
    await safe_edit(callback, text, settings_kb())


@router.callback_query(F.data == "admin:settings:list")
async def settings_list(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    items = await admin_settings_list(session)
    lines = ["🧩 <b>Runtime settings</b>"]
    if not items:
        lines.append("\nПока пусто.")
    for item in items:
        value = item.value
        if len(value) > 80:
            value = value[:77] + "..."
        lines.append(f"\n<code>{h(item.key)}</code> = <code>{h(value)}</code>")
    await safe_edit(callback, "\n".join(lines), settings_kb())


@router.callback_query(F.data == "admin:settings:set")
async def settings_set_prompt(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_setting)
    await safe_edit(callback, "✏️ Отправь настройку в формате:\n<code>key=value</code>", admin_back())


@router.message(AdminStates.waiting_setting)
async def settings_set(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    raw = message.text or ""
    if "=" not in raw:
        await message.answer("⛔ Формат: <code>key=value</code>", reply_markup=admin_back())
        return
    key, value = raw.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key or len(key) > 128:
        await message.answer("⛔ Некорректный ключ", reply_markup=admin_back())
        return
    item = await admin_upsert_setting(session, key, value)
    await state.clear()
    await message.answer(f"✅ Runtime setting сохранён\n\n<code>{h(item.key)}</code> = <code>{h(item.value)}</code>", reply_markup=settings_kb())
