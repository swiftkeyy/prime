from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def robokassa_pay(url: str, tariff: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Перейти к оплате", url=url)
    kb.button(text="↩️ Назад", callback_data="prime:robokassa")
    kb.adjust(1)
    return kb.as_markup()


def robokassa_retry() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Повторить оплату", callback_data="prime:robokassa")
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()
