from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def filters_menu(digits_enabled: bool, underscore_enabled: bool, style_mode: str = "clean") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔢 Цифры: {'ON' if digits_enabled else 'OFF'}", callback_data="filters:digits")
    kb.button(text=f"➖ Подчёркивание: {'ON' if underscore_enabled else 'OFF'}", callback_data="filters:underscore")
    style_titles = {
        "clean": "чистый",
        "mixed": "микс",
        "brutal": "брутальный",
        "soft": "мягкий",
        "brand": "брендовый",
        "techno": "техно",
    }
    kb.button(text=f"🎨 Стиль: {style_titles.get(style_mode, style_mode)}", callback_data="filters:style")
    kb.button(text="↩️ Назад", callback_data="search:menu")
    kb.button(text="🏠 В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
