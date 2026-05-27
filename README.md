# PRIME NICK

Production-ready Telegram bot for searching available Telegram usernames with PRIME PASS, Telegram Stars, Robokassa/SBP, promo codes, referrals, admin panel, PostgreSQL, Redis, FastAPI webhook and Railway deployment.

## Stack

- Python 3.11+
- aiogram 3.x
- FastAPI + uvicorn
- PostgreSQL + SQLAlchemy async + asyncpg
- Redis for FSM, antiflood and username cache
- Alembic migrations
- Telegram Stars
- Robokassa Result URL
- Railway webhook deployment

## Local start

1. Create a bot via BotFather and get `BOT_TOKEN`.
2. Create PostgreSQL and Redis locally or via Docker.
3. Copy env example:

```bash
cp .env.example .env
```

4. Fill `.env`:

```env
BOT_TOKEN=123:token
BOT_USERNAME=PRIME_NICK_BOT
ADMIN_IDS=123456789
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/prime_nick
REDIS_URL=redis://localhost:6379/0
RAILWAY_PUBLIC_URL=https://your-public-url.example.com
WEBHOOK_SECRET=strong-random-secret
```

For local webhook testing use a tunnel such as Cloudflare Tunnel, ngrok or localtunnel and put its HTTPS URL into `RAILWAY_PUBLIC_URL`.

5. Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

6. Apply migrations:

```bash
alembic upgrade head
```

7. Run:

```bash
python main.py
```

Health check:

```bash
curl http://localhost:8080/health
```

## Railway deployment

1. Push the project to GitHub.
2. Create a Railway project.
3. Add PostgreSQL and Redis services.
4. Set variables from `.env.example` in Railway Variables.
5. Set `RAILWAY_PUBLIC_URL` to the public Railway domain, for example `https://prime-nick-production.up.railway.app`.
6. Deploy. Railway uses `railway.json` and runs:

```bash
python main.py
```

7. Run migration once from Railway shell or a one-off command:

```bash
alembic upgrade head
```

## Telegram webhook

The app sets webhook on startup:

```text
{RAILWAY_PUBLIC_URL}/telegram/webhook
```

The webhook is protected with `WEBHOOK_SECRET` and Telegram header `X-Telegram-Bot-Api-Secret-Token`.

## Robokassa settings

Set URLs in Robokassa merchant settings:

```text
Result URL:  https://YOUR_DOMAIN/robokassa/result
Success URL: https://YOUR_DOMAIN/robokassa/success
Fail URL:    https://YOUR_DOMAIN/robokassa/fail
```

Use POST for Result URL. PRIME PASS is issued only after Result URL signature verification. Success URL is not trusted as payment confirmation.

Secrets:

```env
ROBOKASSA_LOGIN=
ROBOKASSA_PASSWORD_1=
ROBOKASSA_PASSWORD_2=
ROBOKASSA_TEST_MODE=true
```

## Telegram Stars

Stars payments use currency `XTR`. The bot creates an invoice, validates `pre_checkout_query`, handles `successful_payment`, writes a payment row and activates PRIME PASS.

## Username checker

Production uses only strict MTProto checking through `account.checkUsername`.
Fragment, `t.me` and Bot API checks are disabled for production because they can show occupied names like `roman`, `angel` or `dobro` as free.

Required Railway Variables:

```env
USERNAME_CHECK_MODE=mtproto
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_STRING_SESSION=your_string_session
MTPROTO_CHECK_DELAY_SECONDS=0.35
```

For local tests only:

```env
USERNAME_CHECK_MODE=mock
```

## Admin panel

Command:

```text
/admin
```

Access is only for IDs from `ADMIN_IDS`.

Features:

- overview stats
- user lookup by telegram_id or username
- grant/revoke PRIME PASS
- create promo codes
- broadcast with preview and delayed sending
- recent payments

## Production notes

- Do not log real payment secrets.
- Keep all keys in `.env` / Railway Variables.
- Use Alembic migrations, not `create_all`, in production.
- Run behind HTTPS on Railway.
- Keep `WEBHOOK_SECRET` random and private.
- Robokassa Result URL is the only trusted confirmation source.

## PRIME ADMIN 2.0

Админка открывается командой `/admin` только для Telegram ID из `ADMIN_IDS`.

Что добавлено:

- `📊 Командный центр` — users/search/money/growth метрики, RUB и Stars выручка, hit-rate, PRIME conversion.
- `🩺 Health` — проверка PostgreSQL, Redis, webhook URL, pending updates и pool status.
- `👥 Пользователи` — сегменты: новые, PRIME, топ по поискам, топ по рефералам.
- `👤 PRIME USER CARD` — подробная карточка пользователя с быстрыми действиями.
- Быстрая выдача PRIME: `+1 день`, `+7 дней`, `+30 дней`, `навсегда`, снятие PRIME.
- Управление попытками: `+5`, `+20`, reset free attempts, zero attempts.
- История поиска и платежи конкретного пользователя.
- `🎟 PROMO CONTROL` — создание, список активных, отключение промокодов.
- `💳 PAYMENT RADAR` — фильтры платежей: все, оплаченные, созданные, pending, failed.
- `🧬 Последние поиски` — последние результаты проверки username.
- `📢 BROADCAST CORE` — рассылка по аудитории: все, PRIME, Base; с прогрессом и логированием ошибок.
- `🧩 Runtime Control` — безопасное хранение runtime-флагов в таблице `settings` через `key=value`.

Для Railway используется `start.sh`: сначала `alembic upgrade head`, потом запуск `python main.py` через `exec`, чтобы контейнер оставался Active.

## Строгая проверка username через MTProto

Bot API, `t.me` и Fragment не умеют надёжно проверять, можно ли реально поставить username на аккаунт. Поэтому production-режим PRIME NICK использует только MTProto `account.checkUsername`.

Ник показывается пользователю только если Telegram возвращает `True`, то есть username можно поставить на текущий MTProto-аккаунт прямо сейчас.

### Railway Variables

```env
USERNAME_CHECK_MODE=mtproto
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_STRING_SESSION=your_string_session
MTPROTO_CHECK_DELAY_SECONDS=0.35
```

### Как получить TELEGRAM_STRING_SESSION

Локально установи зависимости и выполни:

```bash
pip install telethon
python scripts/create_telethon_session.py
```

Введи `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, номер телефона, код Telegram и пароль 2FA, если он включён. Скрипт выведет `TELEGRAM_STRING_SESSION`. Добавь его в Railway Variables.

API ID и API Hash создаются в Telegram на `my.telegram.org`.

## Админка: смена цен PRIME PASS

В админке открой `/admin` → `💰 Цены PRIME`.

Можно менять цены отдельно для:

- `СБП / Robokassa` — рубли;
- `Telegram Stars` — звёзды.

Цены сохраняются в таблицу `settings` под ключами:

- `PRIME_1_DAY_PRICE_RUB`
- `PRIME_7_DAYS_PRICE_RUB`
- `PRIME_30_DAYS_PRICE_RUB`
- `PRIME_FOREVER_PRICE_RUB`
- `PRIME_1_DAY_PRICE_STARS`
- `PRIME_7_DAYS_PRICE_STARS`
- `PRIME_30_DAYS_PRICE_STARS`
- `PRIME_FOREVER_PRICE_STARS`

Если runtime-цена удалена или сломана, бот безопасно использует цену из `.env`. Уже созданные счета не меняются: сумма хранится в `payments.amount`, поэтому старые Robokassa/Stars платежи не ломаются.
