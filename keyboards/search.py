from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def search_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💠 5 символов · PRIME", callback_data="search:length:5")
    kb.button(text="⚡ 6 символов", callback_data="search:length:6")
    kb.button(text="🚀 7 символов", callback_data="search:length:7")
    kb.button(text="🎛 Настроить фильтры", callback_data="filters:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def prime_locked() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💠 Открыть PRIME PASS", callback_data="prime:menu")
    kb.button(text="↩️ Назад", callback_data="search:menu")
    kb.adjust(1)
    return kb.as_markup()


def result(username: str, length: int) -> InlineKeyboardMarkup:
    raw = username.lstrip("@")
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Открыть в Telegram", url=f"https://t.me/{raw}")
    kb.button(text="🔁 Искать ещё", callback_data=f"search:length:{length}")
    kb.button(text="🎛 Фильтры", callback_data="filters:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def retry(length: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if length:
        kb.button(text="🔁 Повторить поиск", callback_data=f"search:length:{length}")
    else:
        kb.button(text="🔁 Повторить поиск", callback_data="search:menu")
    kb.button(text="🎛 Изменить фильтры", callback_data="filters:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
