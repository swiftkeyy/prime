from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


ADMIN_MODES = {
    "latest": "Новые",
    "prime": "PRIME",
    "top_searches": "Топ поиска",
    "top_refs": "Топ рефов",
}

PAYMENT_FILTERS = {
    "all": "Все",
    "paid": "Оплачены",
    "created": "Созданы",
    "pending": "Ожидают",
    "failed": "Ошибки",
}

BROADCAST_AUDIENCES = {
    "all": "Все пользователи",
    "prime": "Только PRIME",
    "base": "Только Base",
}


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Командный центр", callback_data="admin:stats")
    kb.button(text="🩺 Health", callback_data="admin:health")
    kb.button(text="👥 Пользователи", callback_data="admin:users")
    kb.button(text="🔎 Найти юзера", callback_data="admin:user")
    kb.button(text="💠 PRIME Control", callback_data="admin:prime_control")
    kb.button(text="🎟 Промокоды", callback_data="admin:promo")
    kb.button(text="💳 Платежи", callback_data="admin:payments")
    kb.button(text="💰 Цены PRIME", callback_data="admin:prices")
    kb.button(text="🧬 Поиски", callback_data="admin:searches")
    kb.button(text="📢 Рассылка", callback_data="admin:broadcast")
    kb.button(text="🧩 Runtime", callback_data="admin:settings")
    kb.button(text="↩️ Закрыть", callback_data="main:home")
    kb.adjust(2, 2, 2, 2, 2, 1, 1)
    return kb.as_markup()


def admin_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="↩️ В админку", callback_data="admin:menu")
    return kb.as_markup()


def admin_close_back() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚙️ Админка", callback_data="admin:menu")
    kb.button(text="🏠 В меню", callback_data="main:home")
    kb.adjust(2)
    return kb.as_markup()


def users_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🆕 Новые", callback_data="admin:users:latest:0")
    kb.button(text="💠 PRIME", callback_data="admin:users:prime:0")
    kb.button(text="🧬 Топ поиска", callback_data="admin:users:top_searches:0")
    kb.button(text="🔗 Топ рефов", callback_data="admin:users:top_refs:0")
    kb.button(text="🔎 Найти", callback_data="admin:user")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(2, 2, 2)
    return kb.as_markup()


def users_page_kb(users: list, mode: str, page: int, total: int, limit: int = 8) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for user in users:
        handle = f"@{user.username}" if user.username else str(user.telegram_id)
        label = f"👤 {handle} · {user.total_searches}🔎 · {user.referrals_count}🔗"
        kb.button(text=label[:64], callback_data=f"admin:usercard:{user.telegram_id}")
    prev_page = max(0, page - 1)
    next_page = page + 1
    if page > 0:
        kb.button(text="⬅️ Назад", callback_data=f"admin:users:{mode}:{prev_page}")
    if (page + 1) * limit < total:
        kb.button(text="➡️ Далее", callback_data=f"admin:users:{mode}:{next_page}")
    kb.button(text="👥 Раздел", callback_data="admin:users")
    kb.button(text="⚙️ Админка", callback_data="admin:menu")
    kb.adjust(*([1] * len(users)), 2, 2)
    return kb.as_markup()


def user_card_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⚡ +1 день", callback_data=f"admin:userprime:{telegram_id}:1d")
    kb.button(text="🚀 +7 дней", callback_data=f"admin:userprime:{telegram_id}:7d")
    kb.button(text="💠 +30 дней", callback_data=f"admin:userprime:{telegram_id}:30d")
    kb.button(text="♾ Навсегда", callback_data=f"admin:userprime:{telegram_id}:forever")
    kb.button(text="⛔ Забрать PRIME", callback_data=f"admin:userprime:{telegram_id}:revoke")
    kb.button(text="🎯 +5 попыток", callback_data=f"admin:userattempts:{telegram_id}:add5")
    kb.button(text="🎯 +20 попыток", callback_data=f"admin:userattempts:{telegram_id}:add20")
    kb.button(text="🔄 Reset free", callback_data=f"admin:userattempts:{telegram_id}:reset")
    kb.button(text="🧬 История поиска", callback_data=f"admin:usersearches:{telegram_id}")
    kb.button(text="💳 Платежи", callback_data=f"admin:userpayments:{telegram_id}")
    kb.button(text="🔁 Обновить", callback_data=f"admin:usercard:{telegram_id}")
    kb.button(text="↩️ Пользователи", callback_data="admin:users")
    kb.adjust(2, 2, 1, 2, 2, 2, 1)
    return kb.as_markup()


def prime_control_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💠 Выдать вручную", callback_data="admin:give_prime")
    kb.button(text="⛔ Забрать вручную", callback_data="admin:remove_prime")
    kb.button(text="👥 PRIME список", callback_data="admin:users:prime:0")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def promo_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Создать", callback_data="admin:promo:create")
    kb.button(text="📋 Активные", callback_data="admin:promo:list")
    kb.button(text="🧯 Отключить по ID", callback_data="admin:promo:disable_prompt")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def promo_list_kb(promos: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for promo in promos:
        kb.button(text=f"⛔ #{promo.id} {promo.code}", callback_data=f"admin:promo:disable:{promo.id}")
    kb.button(text="➕ Создать", callback_data="admin:promo:create")
    kb.button(text="↩️ Промокоды", callback_data="admin:promo")
    kb.adjust(*([1] * len(promos)), 2)
    return kb.as_markup()


def payments_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, title in PAYMENT_FILTERS.items():
        kb.button(text=f"💳 {title}", callback_data=f"admin:payments:{key}")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(2, 2, 1, 1)
    return kb.as_markup()


def searches_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 Обновить", callback_data="admin:searches")
    kb.button(text="⚙️ Админка", callback_data="admin:menu")
    kb.adjust(2)
    return kb.as_markup()


def broadcast_audience_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🌐 Всем", callback_data="admin:broadcast:audience:all")
    kb.button(text="💠 PRIME", callback_data="admin:broadcast:audience:prime")
    kb.button(text="🛡 Base", callback_data="admin:broadcast:audience:base")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(3, 1)
    return kb.as_markup()


def broadcast_confirm(audience: str = "all") -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="admin:broadcast:send")
    kb.button(text="❌ Отмена", callback_data="admin:broadcast:cancel")
    kb.button(text=f"🎯 {BROADCAST_AUDIENCES.get(audience, audience)}", callback_data="admin:broadcast")
    kb.adjust(2, 1)
    return kb.as_markup()


def prices_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="💳 RUB / Platega", callback_data="admin:prices:platega")
    kb.button(text="⭐ Telegram Stars", callback_data="admin:prices:stars")
    kb.button(text="📋 Все цены", callback_data="admin:prices")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(1)
    return kb.as_markup()


def price_method_kb(method: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    labels = {
        "1d": "⚡ 24 часа",
        "7d": "🚀 7 дней",
        "30d": "💠 30 дней",
        "forever": "♾ Навсегда",
    }
    for tariff, label in labels.items():
        kb.button(text=f"✏️ {label}", callback_data=f"admin:price:set:{method}:{tariff}")
    kb.button(text="↩️ К ценам", callback_data="admin:prices")
    kb.adjust(1)
    return kb.as_markup()


def settings_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📋 Список", callback_data="admin:settings:list")
    kb.button(text="✏️ Set key=value", callback_data="admin:settings:set")
    kb.button(text="↩️ Назад", callback_data="admin:menu")
    kb.adjust(2, 1)
    return kb.as_markup()
