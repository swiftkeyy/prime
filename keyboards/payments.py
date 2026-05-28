from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def platega_pay(url: str, tariff: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Перейти к оплате", url=url)
    kb.button(text="↩️ Назад", callback_data="prime:platega")
    kb.adjust(1)
    return kb.as_markup()


def platega_retry() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Повторить оплату", callback_data="prime:platega")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
