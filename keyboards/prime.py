from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def prime_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⭐ Telegram Stars", callback_data="prime:stars")
    kb.button(text="💳 СБП / Platega", callback_data="prime:platega")
    kb.button(text="🎟 Активировать промокод", callback_data="promo:start")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def tariffs(method: str, prices: dict[str, int], currency_suffix: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    labels = {
        "1d": "⚡ 24 часа",
        "7d": "🚀 7 дней",
        "30d": "💠 30 дней",
        "forever": "♾ Навсегда",
    }
    for tariff, label in labels.items():
        kb.button(text=f"{label} — {prices[tariff]} {currency_suffix}", callback_data=f"prime:tariff:{method}:{tariff}")
    kb.button(text="↩️ Назад", callback_data="prime:menu")
    kb.adjust(1)
    return kb.as_markup()


def prime_success() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Начать поиск", callback_data="search:menu")
    kb.button(text="🛡 Мой профиль", callback_data="profile:open")
    kb.adjust(1)
    return kb.as_markup()


def prime_locked_cta() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💠 Открыть PRIME PASS", callback_data="prime:menu")
    kb.button(text="🏠 В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
