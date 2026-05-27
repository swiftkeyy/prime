from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Сканировать ник", callback_data="search:menu")
    kb.button(text="💠 PRIME PASS", callback_data="prime:menu")
    kb.button(text="🛡 Мой профиль", callback_data="profile:open")
    kb.button(text="🎛 Фильтры", callback_data="filters:menu")
    kb.button(text="🗂 Правила", callback_data="docs:open")
    kb.button(text="📡 Связь", callback_data="support:open")
    kb.adjust(1, 1, 2, 2)
    return kb.as_markup()


def back_home() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ В меню", callback_data="main:home")
    return kb.as_markup()
