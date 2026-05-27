from __future__ import annotations

from config import Settings
from database.models import User
from utils.referrals import make_referral_link
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


def generating_for_length(length: int, max_candidates: int) -> str:
    if length == 5:
        return f"""🧬 <b>Глубокий PRIME-скан...</b>

5-символьные username почти всегда заняты.
Проверяю расширенный пул красивых вариантов: до {max_candidates} кандидатов."""

    return GENERATING

NOT_FOUND = """⏳ <b>Ничего подходящего</b>

Свободный username не найден в текущем режиме.
Для 5 символов это нормально: короткие чистые ники почти всегда заняты. Попробуй включить цифры в фильтрах или запусти повторный скан."""

CHECK_UNAVAILABLE = """⚠️ <b>Проверка сейчас недоступна</b>

Проверка username работает через Telegram MTProto.
Если ошибка повторяется — проверь TELEGRAM_STRING_SESSION в Railway."""

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


def profile(
    user: User,
    settings: Settings,
    time_left: str,
    attempts_total: int,
    reserved_count: int = 0,
    reserved_limit: int = 10,
    bot_username: str | None = None,
) -> str:
    status = "PRIME PASS" if user.is_prime else "Base"
    prime_until = format_dt(user.prime_until) if user.is_prime else "не активен"
    link = make_referral_link(bot_username or settings.BOT_USERNAME, user)
    return f"""🛡 <b>PRIME ID</b>

╭─ <b>Аккаунт</b>
│ ID: <code>{user.telegram_id}</code>
│ Статус: <b>{status}</b>
│ Поисков выполнено: <b>{user.total_searches}</b>
│ Доступных попыток: <b>{attempts_total}</b>
│ Резервы username: <b>{reserved_count}/{reserved_limit}</b>
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
    link = getattr(settings, "LEGAL_INFO_LINK", "") or "https://telegra.ph/Oplata-oferta-vozvrat-i-obrabotka-dannyh-PRIME-NICK-05-27"
    return f"""🗂 <b>Правовая информация PRIME NICK</b>

Перед использованием сервиса ознакомься с документом:

• <b>Правовая информация, оплата и возврат</b>
{h(link)}"""


def robokassa_invoice(tariff: str, amount: int) -> str:
    return f"""💳 <b>Оплата через СБП</b>

Тариф: <b>{tariff_title(tariff)}</b>
Сумма: <b>{amount} ₽</b>

Нажми кнопку ниже, чтобы перейти к оплате."""


def promo_success(days: int) -> str:
    return f"""✅ <b>Промокод принят</b>

На аккаунт начислен PRIME PASS на <b>{days}</b> дней."""

def reserve_success(username: str, used: int, limit: int) -> str:
    raw = username.lstrip("@")
    return f"""✅ <b>Ник зарезервирован</b>

@{h(raw)} закреплён за твоим аккаунтом в PRIME NICK.
Теперь этот username не будет выпадать другим пользователям бота.

Резервы: <b>{used}/{limit}</b>"""


def reserve_already_own(username: str, used: int, limit: int) -> str:
    raw = username.lstrip("@")
    return f"""🧷 <b>Уже в резерве</b>

@{h(raw)} уже закреплён за твоим аккаунтом.

Резервы: <b>{used}/{limit}</b>"""


def reserve_taken(username: str) -> str:
    raw = username.lstrip("@")
    return f"""⛔ <b>Ник уже зарезервирован</b>

@{h(raw)} уже закреплён за другим пользователем PRIME NICK.
Он больше не будет попадать в выдачу."""


def reserve_limit_reached(limit: int) -> str:
    return f"""⛔ <b>Лимит резервов</b>

Ты уже зарезервировал максимум: <b>{limit}</b> username.

Base лимит: <b>10</b>
PRIME PASS лимит: <b>30</b>"""


def reservations_list_text(reservations: list, used: int, limit: int) -> str:
    if not reservations:
        return f"""🧷 <b>Мои резервы</b>

Пока нет закреплённых username.
Найди свободный ник и нажми <b>«Зарезервировать»</b>.

Лимит: <b>{used}/{limit}</b>"""

    lines = []
    for idx, item in enumerate(reservations[:30], start=1):
        lines.append(f"{idx}. @{h(item.username)} · {h(str(item.length))} симв.")
    joined = "\n".join(lines)
    return f"""🧷 <b>Мои резервы</b>

Закреплено: <b>{used}/{limit}</b>

{joined}

Нажми на ник ниже, чтобы освободить резерв."""


def reservation_released(username: str) -> str:
    raw = username.lstrip("@")
    return f"""✅ <b>Резерв снят</b>

@{h(raw)} снова может появляться в выдаче PRIME NICK."""

CUSTOM_NICK_PROMPT = """✨ <b>Подбор по слову</b>

Напиши, какой ник хочешь получить.
Можно отправить имя, слово, @username или ссылку t.me.

Я соберу до <b>5 красивых вариантов</b> и проверю их напрямую через Telegram."""

CUSTOM_NICK_GENERATING = """🧬 <b>Собираю варианты...</b>

Делаю ник читаемым, красивым и проверяю доступность."""

CUSTOM_NICK_BAD_INPUT = """⛔ <b>Не могу собрать ник</b>

Отправь слово или основу ника: например <code>dobro</code>, <code>nikita</code>, <code>zapor</code>."""


def custom_nick_results(seed: str, usernames: list[str]) -> str:
    lines = []
    for idx, username in enumerate(usernames[:5], start=1):
        raw = username.lstrip("@")
        lines.append(f"{idx}. @{h(raw)}")
    joined = "\n".join(lines)
    return f"""✅ <b>Варианты найдены</b>

Основа: <b>{h(seed)}</b>

╭─ <b>PRIME IDEAS</b>
{joined}
╰ Нажми на ник, чтобы открыть, или на 🧷, чтобы зарезервировать."""


def custom_nick_not_found(seed: str) -> str:
    return f"""⏳ <b>Свободные варианты не найдены</b>

По основе <b>{h(seed)}</b> сейчас не удалось найти свободный красивый ник.

Попробуй другое слово, более короткую основу или включи цифры в фильтрах."""
