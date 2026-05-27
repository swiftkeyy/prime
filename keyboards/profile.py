from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def profile_menu(ref_link: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💠 Получить PRIME PASS", callback_data="prime:menu")
    kb.button(text="🔗 Моя ссылка", url=ref_link)
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
