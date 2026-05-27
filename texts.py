from __future__ import annotations

from config import Settings
from database.models import User
from utils.formatters import h, money_rub, tariff_title
from utils.time import format_dt, human_time_left

BRAND = "PRIME NICK"

WELCOME = """⚡ <b>PRIME NICK</b>

Умный сканер свободных Telegram username.

Находи короткие ники, проверяй доступность и забирай лучшие варианты раньше других.

Выбери действие ниже:"""

SEARCH_MENU = """🔎 <b>Режим сканирования</b>

Выбери длину username.
Чем короче ник — тем выше его ценность.

Доступные режимы:"""

PRIME_LOCKED = """⛔ <b>Закрытый режим</b>

Поиск username из 5 символов доступен только с <b>PRIME PASS</b>.

С PRIME PASS ты получаешь:
• доступ к коротким никам
• больше попыток поиска
• ускоренную проверку
• расширенные фильтры
• приоритетную связь"""

GENERATING = """🧬 <b>Запускаю генерацию...</b>

Проверяю свободные username и отбираю подходящий вариант."""

NOT_FOUND = """⏳ <b>Ничего подходящего</b>

Свободный username не найден в текущем режиме.
Попробуй другую длину или измени фильтры."""

CHECK_UNAVAILABLE = """⚠️ <b>Проверка временно недоступна</b>

Попробуй повторить запрос немного позже."""

UNKNOWN_ERROR = """⚠️ <b>Что-то пошло не так</b>

Попробуй повторить действие чуть позже."""

ANTIFLOOD = """⏳ <b>Слишком быстро</b>

Подожди пару секунд и попробуй снова."""

FILTERS_SAVED = """✅ <b>Фильтры сохранены</b>

Новые параметры будут применены при следующем поиске."""

PRIME_ACTIVATED = """✅ <b>PRIME PASS активирован</b>

Теперь тебе открыт расширенный режим PRIME NICK:

• 5-символьные username
• больше попыток поиска
• быстрый скан
• расширенные фильтры
• приоритетная связь"""

ROBOKASSA_SUCCESS = """✅ <b>Оплата получена</b>

💠 <b>PRIME PASS активирован.</b>

Теперь тебе доступны:
• короткие username
• больше попыток поиска
• быстрый скан
• расширенные фильтры"""

ROBOKASSA_FAIL = """⛔ <b>Оплата не завершена</b>

Попробуй ещё раз или выбери другой тариф."""

PROMO_START = """🎟 <b>Активация промокода</b>

Отправь промокод одним сообщением."""

PROMO_ERROR = """⛔ <b>Промокод недоступен</b>

Возможно, он уже использован, истёк или введён неверно."""

REFERRAL_BONUS = """🎉 <b>Новый пользователь по твоей ссылке</b>

Тебе начислен бонус:
+{bonus} попыток"""

SUPPORT = """📡 <b>Связь с PRIME NICK</b>

Мы отвечаем по вопросам:
• оплаты
• PRIME PASS
• промокодов
• ошибок поиска
• сотрудничества

Время ответа:
12:00 — 00:00 МСК"""

PRIME_MENU = """💠 <b>PRIME PASS</b>

Расширенный доступ к поиску редких Telegram username.

Что входит:

⚡ быстрый поиск
🔎 больше проверок
💠 5-символьные username
🎛 расширенные фильтры
📡 приоритетная связь
🎟 доступ к промокодам и акциям

Выбери способ оплаты:"""

TARIFFS_HEADER = "💠 <b>Выбери срок PRIME PASS</b>"


def username_found(username: str) -> str:
    raw = username.lstrip("@")
    return f"""✅ <b>Username найден</b>

Вариант свободен на момент проверки:

╭─ <b>PRIME RESULT</b>
│
├ username: @{h(raw)}
├ telegram: t.me/{h(raw)}
└ web: {h(raw)}.t.me
│
╰ Забирай быстрее — короткие ники долго не живут."""


def filters_menu(user: User) -> str:
    digits = "ON" if user.digits_enabled else "OFF"
    underscore = "ON" if user.underscore_enabled else "OFF"
    return f"""🎛 <b>Фильтры PRIME NICK</b>

Минимальные настройки генерации.
Без лишних режимов — только то, что влияет на ник.

╭─ <b>Сейчас</b>
│ Цифры: <b>{digits}</b>
╰ Подчёркивание: <b>{underscore}</b>"""


def profile(user: User, settings: Settings, time_left: str, attempts_total: int) -> str:
    status = "PRIME PASS" if user.is_prime else "Base"
    prime_until = format_dt(user.prime_until) if user.is_prime else "не активен"
    link = f"https://t.me/{settings.BOT_USERNAME}?start={user.telegram_id}"
    return f"""🛡 <b>PRIME ID</b>

╭─ <b>Аккаунт</b>
│ ID: <code>{user.telegram_id}</code>
│ Статус: <b>{status}</b>
│ Поисков выполнено: <b>{user.total_searches}</b>
│ Доступных попыток: <b>{attempts_total}</b>
╰ PRIME до: <b>{prime_until}</b>

╭─ <b>Реферальная система</b>
│ Приглашено: <b>{user.referrals_count}</b>
│ Твоя ссылка:
│ <code>{link}</code>
╰ Бонус: +{settings.REFERRAL_BONUS_ATTEMPTS} попыток за друга

Следующее обновление попыток:
⏳ <b>{time_left}</b>"""


def attempts_limit(time_left: str) -> str:
    return f"""⏳ <b>Лимит поиска исчерпан</b>

Бесплатные попытки обновятся через:
<b>{time_left}</b>

Хочешь искать без ожидания?
Открой PRIME PASS и получи расширенный доступ."""


def rules(settings: Settings) -> str:
    return f"""🗂 <b>Правила PRIME NICK</b>

Перед использованием сервиса ознакомься с документами:

• Пользовательское соглашение
{h(settings.USER_AGREEMENT_LINK or "ссылка не задана")}

• Политика конфиденциальности
{h(settings.PRIVACY_POLICY_LINK or "ссылка не задана")}

• Условия PRIME PASS
{h(settings.PRIME_TERMS_LINK or "ссылка не задана")}"""


def robokassa_invoice(tariff: str, amount: int) -> str:
    return f"""💳 <b>Оплата через СБП</b>

Тариф: <b>{tariff_title(tariff)}</b>
Сумма: <b>{amount} ₽</b>

Нажми кнопку ниже, чтобы перейти к оплате."""


def promo_success(days: int) -> str:
    return f"""✅ <b>Промокод принят</b>

На аккаунт начислен PRIME PASS на <b>{days}</b> дней."""
