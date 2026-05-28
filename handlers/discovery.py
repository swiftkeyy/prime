from __future__ import annotations

from datetime import timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import ReservedUsername, Search, User, UsernameStock
from keyboards.discovery import back_discovery, collections_menu, discovery_menu
from keyboards.prime import prime_locked_cta
from redis.asyncio import Redis
from services.drop_alerts import is_subscribed_to_drop_alerts, subscribe_drop_alerts, unsubscribe_drop_alerts
from services.prime_access import is_prime_active
from services.username_score import rarity_line
from texts import PRIME_LAB_LOCKED
from utils.referrals import make_referral_link
from utils.telegram import safe_callback_answer, safe_edit_callback
from utils.time import utcnow

router = Router(name="discovery")

COLLECTIONS = {
    "brutal": ("⚔️ Брутальные", "короткие, резкие, с x/z/v/k в звучании"),
    "soft": ("🌙 Мягкие", "плавные, читаемые, с мягкими гласными"),
    "business": ("💼 Бизнес", "чистые username под личный бренд и проекты"),
    "gaming": ("🎮 Геймерские", "быстрые, запоминающиеся, похожие на теги"),
    "digits": ("🔢 Короткие с цифрой", "5-6 символов с аккуратной цифрой"),
    "brand": ("💎 Псевдо-бренд", "выглядят как название продукта или студии"),
}


def _prime_lab_denied() -> tuple[str, object]:
    return PRIME_LAB_LOCKED, prime_locked_cta()


@router.callback_query(F.data == "discover:menu")
async def discover_menu(callback: CallbackQuery, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    text = """🧪 <b>PRIME Lab</b>

Витрина премиальных механик PRIME NICK.
Здесь ты смотришь на username не как на случайный ник, а как на цифровой актив:

• умные коллекции по вайбу
• дропы свежих проверенных ников
• топ username недели
• оценка редкости
• публичный PRIME Pulse
• реферальный буст"""
    await safe_edit_callback(callback, text, reply_markup=discovery_menu())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:collections")
async def show_collections(callback: CallbackQuery, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    text = """🧬 <b>Умные коллекции</b>

Выбери настроение username.
Коллекции помогают быстрее понять, какой визуальный характер искать в сканере."""
    await safe_edit_callback(callback, text, reply_markup=collections_menu())
    await safe_callback_answer(callback)


@router.callback_query(F.data.startswith("discover:collection:"))
async def collection_detail(callback: CallbackQuery, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    key = callback.data.split(":")[-1]
    title, description = COLLECTIONS.get(key, COLLECTIONS["brand"])
    examples = {
        "brutal": ["vexor", "kravo", "zornx"],
        "soft": ["lurio", "nevan", "sovia"],
        "business": ["varian", "nordic", "solven"],
        "gaming": ["xavor", "revik", "zento"],
        "digits": ["seik2", "voro7", "mixo4"],
        "brand": ["veltor", "novara", "luminor"],
    }.get(key, [])
    text = f"""{title}

Характер: {description}.

Примеры звучания:
{chr(10).join(f"• @{item} · {rarity_line(item)}" for item in examples)}

Открой сканер и подбирай username в этом направлении, если хочешь собрать более цельный образ аккаунта."""
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:drops")
async def daily_drops(callback: CallbackQuery, session: AsyncSession, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    now = utcnow()
    result = await session.scalars(
        select(UsernameStock)
        .where(UsernameStock.status == "available", UsernameStock.expires_at > now)
        .order_by(UsernameStock.checked_at.desc(), UsernameStock.id.desc())
        .limit(8)
    )
    items = list(result)
    if not items:
        text = """🔥 <b>Дропы дня</b>

Сейчас витрина свежих username прогревается.
Загляни чуть позже или запусти сканирование вручную."""
    else:
        lines = [f"• @{item.username} · {rarity_line(item.username)}" for item in items]
        text = "🔥 <b>Дропы дня</b>\n\nСвежие проверенные username из витрины PRIME NICK:\n\n" + "\n".join(lines)
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:weekly")
async def weekly_top(callback: CallbackQuery, session: AsyncSession, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    week_start = utcnow() - timedelta(days=7)
    result = await session.scalars(
        select(Search.username_result)
        .where(Search.created_at >= week_start, Search.username_result.is_not(None))
        .order_by(Search.created_at.desc(), Search.id.desc())
        .limit(40)
    )
    usernames = []
    seen: set[str] = set()
    for item in result:
        username = str(item).lower().lstrip("@")
        if username and username not in seen:
            seen.add(username)
            usernames.append(username)
        if len(usernames) >= 10:
            break

    if not usernames:
        text = """🏆 <b>Топ никнеймов недели</b>

Пока неделя только разгоняется.
Как только накопятся сильные находки, здесь появится weekly ranking."""
    else:
        lines = [f"{idx}. @{username} · {rarity_line(username)}" for idx, username in enumerate(usernames, start=1)]
        text = "🏆 <b>Топ никнеймов недели</b>\n\nЛучшие username, которые проходили через PRIME NICK за последние 7 дней:\n\n" + "\n".join(lines)
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:alerts")
async def drop_alerts_toggle(callback: CallbackQuery, redis: Redis, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    subscribed = await is_subscribed_to_drop_alerts(redis, current_user.telegram_id)
    if subscribed:
        await unsubscribe_drop_alerts(redis, current_user.telegram_id)
        text = """🔔 <b>Drop Alerts выключены</b>

Больше не буду присылать уведомления о свежих дропах.
Включить обратно можно в PRIME Lab в один тап."""
    else:
        await subscribe_drop_alerts(redis, current_user.telegram_id)
        text = """🔔 <b>Drop Alerts включены</b>

Теперь бот будет присылать сигнал, когда в витрине появляются свежие username.
Это помогает забирать сильные варианты раньше остальных."""
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:pulse")
async def prime_pulse(callback: CallbackQuery, session: AsyncSession, current_user: User) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    now = utcnow()
    day_start = now - timedelta(hours=24)
    users = await session.scalar(select(func.count(User.id))) or 0
    searches = await session.scalar(select(func.count(Search.id)).where(Search.created_at >= day_start)) or 0
    found = await session.scalar(select(func.count(Search.id)).where(Search.created_at >= day_start, Search.username_result.is_not(None))) or 0
    reserves = await session.scalar(select(func.count(ReservedUsername.id)).where(ReservedUsername.is_active.is_(True))) or 0
    stock = await session.scalar(select(func.count(UsernameStock.id)).where(UsernameStock.status == "available", UsernameStock.expires_at > now)) or 0
    hit_rate = int((found / searches) * 100) if searches else 0
    text = f"""📊 <b>PRIME Pulse</b>

Живая витрина PRIME NICK:

• пользователей: <b>{users}</b>
• поисков за 24ч: <b>{searches}</b>
• hit-rate за 24ч: <b>{hit_rate}%</b>
• активных резервов: <b>{reserves}</b>
• username в stock: <b>{stock}</b>

Эти цифры дают сильное социальное доказательство и усиливают восприятие продукта."""
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "discover:referrals")
async def referral_boost(callback: CallbackQuery, bot, current_user: User, settings: Settings) -> None:
    if not is_prime_active(current_user):
        text, markup = _prime_lab_denied()
        await safe_edit_callback(callback, text, reply_markup=markup)
        await safe_callback_answer(callback)
        return
    me = await bot.get_me()
    bot_username = me.username or settings.BOT_USERNAME
    link = make_referral_link(bot_username, current_user)
    text = f"""🔗 <b>Реферальный буст</b>

Приглашай людей и усиливай аккаунт дополнительными попытками поиска.

• приглашено: <b>{current_user.referrals_count}</b>
• бонус за друга: <b>+{settings.REFERRAL_BONUS_ATTEMPTS}</b> попытки

Твоя ссылка:
<code>{link}</code>

Лучший текст для сторис:
<i>Нашёл сервис, который помогает забирать сильные Telegram username раньше других. Заходи по моей ссылке.</i>"""
    await safe_edit_callback(callback, text, reply_markup=back_discovery())
    await safe_callback_answer(callback)
