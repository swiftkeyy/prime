from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def search_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ Подобрать по слову", callback_data="search:custom:start")
    kb.button(text="💠 5 символов · PRIME", callback_data="search:length:5")
    kb.button(text="⚡ 6 символов", callback_data="search:length:6")
    kb.button(text="🚀 7 символов", callback_data="search:length:7")
    kb.button(text="🎛 Настроить фильтры", callback_data="filters:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def custom_prompt() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ Назад к поиску", callback_data="search:menu")
    kb.button(text="🏠 В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def custom_results(usernames: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for username in usernames[:5]:
        raw = username.lstrip("@")
        kb.button(text=f"🌐 @{raw}", url=f"https://t.me/{raw}")
        kb.button(text="🧷", callback_data=f"search:reserve:{raw}:{len(raw)}")
    kb.button(text="✨ Подобрать ещё", callback_data="search:custom:start")
    kb.button(text="🔎 Сканирование", callback_data="search:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(2, 2, 2, 1, 1, 1)
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
    kb.button(text="🧷 Зарезервировать", callback_data=f"search:reserve:{raw}:{length}")
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


def reserved_result(username: str, length: int | None = None) -> InlineKeyboardMarkup:
    raw = username.lstrip("@")
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Открыть в Telegram", url=f"https://t.me/{raw}")
    kb.button(text="🧷 Мои резервы", callback_data="profile:reservations")
    if length:
        if length in (5, 6, 7):
            kb.button(text="🔁 Искать ещё", callback_data=f"search:length:{length}")
        else:
            kb.button(text="✨ Подобрать ещё", callback_data="search:custom:start")
    else:
        kb.button(text="🔎 Поиск", callback_data="search:menu")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def reserve_error(length: int | None = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🧷 Мои резервы", callback_data="profile:reservations")
    if length and length in (5, 6, 7):
        kb.button(text="🔁 Искать ещё", callback_data=f"search:length:{length}")
    else:
        kb.button(text="✨ Подобрать по слову", callback_data="search:custom:start")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
