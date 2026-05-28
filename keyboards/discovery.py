from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def discovery_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧬 Умные коллекции", callback_data="discover:collections")
    kb.button(text="🔥 Дропы дня", callback_data="discover:drops")
    kb.button(text="🏆 Топ недели", callback_data="discover:weekly")
    kb.button(text="🔔 Drop Alerts", callback_data="discover:alerts")
    kb.button(text="📊 PRIME Pulse", callback_data="discover:pulse")
    kb.button(text="🔗 Реферальный буст", callback_data="discover:referrals")
    kb.button(text="✨ Подбор под бренд", callback_data="search:custom:start")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def collections_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, title in (
        ("brutal", "⚔️ Брутальные"),
        ("soft", "🌙 Мягкие"),
        ("business", "💼 Бизнес"),
        ("gaming", "🎮 Геймерские"),
        ("digits", "🔢 Короткие с цифрой"),
        ("brand", "💎 Псевдо-бренд"),
    ):
        kb.button(text=title, callback_data=f"discover:collection:{key}")
    kb.button(text="↩️ Назад", callback_data="discover:menu")
    kb.adjust(1, 1, 1, 1, 1, 1, 1)
    return kb.as_markup()


def back_discovery() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Сканировать", callback_data="search:menu")
    kb.button(text="↩️ В PRIME Lab", callback_data="discover:menu")
    kb.button(text="🏠 В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
