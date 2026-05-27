from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Обзор", callback_data="admin:stats")
    kb.button(text="👤 Пользователь", callback_data="admin:user")
    kb.button(text="💠 Выдать PRIME", callback_data="admin:give_prime")
    kb.button(text="⛔ Забрать PRIME", callback_data="admin:remove_prime")
    kb.button(text="🎟 Промокоды", callback_data="admin:promo")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="💳 Платежи", callback_data="admin:payments")
    kb.button(text="🧩 Настройки", callback_data="admin:settings")
    kb.button(text="↩️ Закрыть", callback_data="main:home")
    kb.adjust(2, 2, 2, 2, 1)
    return kb.as_markup()


def admin_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ В админку", callback_data="admin:menu")
    return kb.as_markup()


def broadcast_confirm() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="admin:broadcast:send")
    kb.button(text="❌ Отмена", callback_data="admin:broadcast:cancel")
    kb.adjust(2)
    return kb.as_markup()
