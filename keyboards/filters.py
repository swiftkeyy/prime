from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def filters_menu(digits_enabled: bool, underscore_enabled: bool) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=f"🔢 Цифры: {'ON' if digits_enabled else 'OFF'}", callback_data="filters:digits")
    kb.button(text=f"➖ Underscore: {'ON' if underscore_enabled else 'OFF'}", callback_data="filters:underscore")
    kb.button(text="🧼 Только буквы", callback_data="filters:letters")
    kb.button(text="🧪 Смешанный стиль", callback_data="filters:mixed")
    kb.button(text="✅ Сохранить", callback_data="filters:save")
    kb.button(text="↩️ Назад", callback_data="search:menu")
    kb.adjust(1)
    return kb.as_markup()
