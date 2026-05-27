from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.queries import (
    all_user_telegram_ids,
    create_promo_code,
    get_user_by_id_or_username,
    recent_payments,
    stats_overview,
)
from keyboards.admin import admin_back, admin_menu, broadcast_confirm
from services.prime_access import grant_prime, revoke_prime
from utils.formatters import h, money_rub, tariff_title
from utils.time import format_dt
from utils.validators import normalize_promo

router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_user = State()
    waiting_give_prime = State()
    waiting_remove_prime = State()
    waiting_promo = State()
    waiting_broadcast = State()
    preview_broadcast = State()


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_id_set


async def deny(message_or_callback, settings: Settings) -> bool:
    user = message_or_callback.from_user
    if not user or not is_admin(user.id, settings):
        if isinstance(message_or_callback, CallbackQuery):
            await message_or_callback.answer("Нет доступа", show_alert=True)
        else:
            await message_or_callback.answer("⛔ Нет доступа")
        return True
    return False


@router.message(Command("admin"))
async def cmd_admin(message: Message, settings: Settings) -> None:
    if await deny(message, settings):
        return
    await message.answer("⚙️ <b>PRIME ADMIN</b>", reply_markup=admin_menu())


@router.callback_query(F.data == "admin:menu")
async def admin_home(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await callback.message.edit_text("⚙️ <b>PRIME ADMIN</b>", reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    s = await stats_overview(session)
    text = f"""📊 <b>PRIME NICK · Обзор</b>

Пользователей: <b>{s['users_count']}</b>
PRIME PASS: <b>{s['prime_count']}</b>
Поисков всего: <b>{s['searches_count']}</b>
Поисков сегодня: <b>{s['today_searches']}</b>
Оплат: <b>{s['payments_count']}</b>
Доход: <b>{money_rub(s['revenue'])}</b>
Новых за сегодня: <b>{s['today_users']}</b>"""
    await callback.message.edit_text(text, reply_markup=admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin:user")
async def ask_user(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_user)
    await callback.message.edit_text("👤 Отправь telegram_id или @username пользователя.", reply_markup=admin_back())
    await callback.answer()


@router.message(AdminStates.waiting_user)
async def show_user(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    if await deny(message, settings):
        return
    user = await get_user_by_id_or_username(session, message.text or "")
    await state.clear()
    if not user:
        await message.answer("⛔ Пользователь не найден", reply_markup=admin_back())
        return
    text = f"""👤 <b>Пользователь</b>

ID: <code>{user.telegram_id}</code>
Username: @{h(user.username or '—')}
Имя: {h(user.first_name or '—')}
Статус: <b>{'PRIME PASS' if user.is_prime else 'Base'}</b>
PRIME до: <b>{format_dt(user.prime_until) if user.is_prime else 'не активен'}</b>
Попытки: <b>{user.attempts_left}</b>
Бонусные: <b>{user.bonus_attempts}</b>
Поиски: <b>{user.total_searches}</b>
Рефералы: <b>{user.referrals_count}</b>"""
    await message.answer(text, reply_markup=admin_back())


@router.callback_query(F.data == "admin:give_prime")
async def ask_give_prime(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_give_prime)
    await callback.message.edit_text(
        "💠 Отправь: <code>telegram_id срок</code>\n\nСрок: <code>1d</code>, <code>7d</code>, <code>30d</code>, <code>forever</code>",
        reply_markup=admin_back(),
    )
    await callback.answer()


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
    await message.answer(f"✅ PRIME PASS выдан: <code>{user.telegram_id}</code> · {tariff_title(parts[1])}", reply_markup=admin_back())


@router.callback_query(F.data == "admin:remove_prime")
async def ask_remove_prime(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_remove_prime)
    await callback.message.edit_text("⛔ Отправь telegram_id пользователя, у которого нужно забрать PRIME PASS.", reply_markup=admin_back())
    await callback.answer()


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
    await message.answer(f"✅ PRIME PASS отключён: <code>{user.telegram_id}</code>", reply_markup=admin_back())


@router.callback_query(F.data == "admin:promo")
async def ask_promo(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_promo)
    await callback.message.edit_text(
        "🎟 Отправь промокод в формате:\n<code>CODE days max_uses YYYY-MM-DD</code>\n\nДата окончания необязательна: <code>PRIME7 7 100</code>",
        reply_markup=admin_back(),
    )
    await callback.answer()


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
    except Exception:  # noqa: BLE001
        await message.answer("⛔ Не удалось разобрать промокод", reply_markup=admin_back())
        return
    promo = await create_promo_code(session, code, days, max_uses, expires_at)
    await state.clear()
    await message.answer(f"✅ Промокод создан: <code>{promo.code}</code> · {days} дней · лимит {max_uses}", reply_markup=admin_back())


@router.callback_query(F.data == "admin:broadcast")
async def ask_broadcast(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await callback.message.edit_text("📢 Отправь текст рассылки. HTML-разметка поддерживается.", reply_markup=admin_back())
    await callback.answer()


@router.message(AdminStates.waiting_broadcast)
async def preview_broadcast(message: Message, state: FSMContext, settings: Settings) -> None:
    if await deny(message, settings):
        return
    await state.update_data(text=message.html_text or message.text or "")
    await state.set_state(AdminStates.preview_broadcast)
    await message.answer("📢 <b>Предпросмотр рассылки</b>\n\n" + (message.html_text or message.text or ""), reply_markup=broadcast_confirm())


@router.callback_query(F.data == "admin:broadcast:cancel")
async def cancel_broadcast(callback: CallbackQuery, state: FSMContext, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена", reply_markup=admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin:broadcast:send")
async def send_broadcast(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    data = await state.get_data()
    text = data.get("text")
    if not text:
        await callback.answer("Текст не найден", show_alert=True)
        return
    ids = await all_user_telegram_ids(session)
    sent = failed = 0
    await callback.message.edit_text("📢 Рассылка запущена...")
    for chat_id in ids:
        try:
            await bot.send_message(chat_id, text)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        await asyncio.sleep(0.08)
    await state.clear()
    await callback.message.answer(f"✅ Рассылка завершена\n\nОтправлено: <b>{sent}</b>\nОшибок: <b>{failed}</b>", reply_markup=admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin:payments")
async def payments(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    items = await recent_payments(session, 10)
    if not items:
        await callback.message.edit_text("💳 Платежей пока нет", reply_markup=admin_back())
        await callback.answer()
        return
    lines = ["💳 <b>Последние платежи</b>"]
    for p in items:
        lines.append(
            f"\n#{p.id} · user_id={p.user_id}\n"
            f"{money_rub(p.amount) if p.currency == 'RUB' else str(int(p.amount)) + ' ⭐'} · {p.method} · {p.status}\n"
            f"тариф: {p.tariff}"
        )
    await callback.message.edit_text("\n".join(lines), reply_markup=admin_back())
    await callback.answer()


@router.callback_query(F.data == "admin:settings")
async def settings_stub(callback: CallbackQuery, settings: Settings) -> None:
    if await deny(callback, settings):
        return
    await callback.message.edit_text("🧩 Настройки хранятся в .env и таблице settings. Безопасные runtime-переключатели можно добавить поверх этой панели.", reply_markup=admin_back())
    await callback.answer()
