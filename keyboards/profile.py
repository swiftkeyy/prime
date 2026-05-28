from urllib.parse import quote_plus

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def profile_menu(ref_link: str) -> InlineKeyboardMarkup:
    share_text = "PRIME NICK — поиск свободных Telegram username"
    share_url = f"https://t.me/share/url?url={quote_plus(ref_link)}&text={quote_plus(share_text)}"

    kb = InlineKeyboardBuilder()
    kb.button(text="💠 Получить PRIME PASS", callback_data="prime:menu")
    kb.button(text="🧷 Мои резервы", callback_data="profile:reservations")
    kb.button(text="🏆 Мои лучшие находки", callback_data="profile:best")
    kb.button(text="📤 Пригласить друга", url=share_url)
    kb.button(text="🔗 Открыть реф-ссылку", url=ref_link)
    kb.button(text="↩️ В меню", callback_data="main:home")
    kb.adjust(1)
    return kb.as_markup()


def reservations_menu(reservations: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in reservations[:30]:
        kb.button(text=f"✖ @{item.username}", callback_data=f"profile:reservation:release:{item.id}")
    kb.button(text="🔎 Искать ники", callback_data="search:menu")
    kb.button(text="↩️ В профиль", callback_data="profile:open")
    kb.button(text="🏠 В меню", callback_data="main:home")
    if reservations:
        kb.adjust(*([1] * min(len(reservations), 30)), 1, 2)
    else:
        kb.adjust(1, 2)
    return kb.as_markup()
