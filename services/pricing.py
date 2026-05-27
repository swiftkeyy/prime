from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Setting

PaymentMethod = Literal["robokassa", "stars"]
Tariff = Literal["1d", "7d", "30d", "forever"]

TARIFFS: tuple[str, ...] = ("1d", "7d", "30d", "forever")
METHODS: tuple[str, ...] = ("robokassa", "stars")

RUB_KEYS = {
    "1d": "PRIME_1_DAY_PRICE_RUB",
    "7d": "PRIME_7_DAYS_PRICE_RUB",
    "30d": "PRIME_30_DAYS_PRICE_RUB",
    "forever": "PRIME_FOREVER_PRICE_RUB",
}

STARS_KEYS = {
    "1d": "PRIME_1_DAY_PRICE_STARS",
    "7d": "PRIME_7_DAYS_PRICE_STARS",
    "30d": "PRIME_30_DAYS_PRICE_STARS",
    "forever": "PRIME_FOREVER_PRICE_STARS",
}

METHOD_TITLES = {
    "robokassa": "СБП / Robokassa",
    "stars": "Telegram Stars",
}

METHOD_CURRENCIES = {
    "robokassa": "₽",
    "stars": "⭐",
}


@dataclass(frozen=True)
class PriceView:
    method: str
    tariff: str
    amount: int
    key: str
    source: str


def price_key(method: str, tariff: str) -> str:
    if tariff not in TARIFFS:
        raise ValueError("unknown tariff")
    if method == "robokassa":
        return RUB_KEYS[tariff]
    if method == "stars":
        return STARS_KEYS[tariff]
    raise ValueError("unknown payment method")


def fallback_price(settings: Settings, method: str, tariff: str) -> int:
    if method == "robokassa":
        return settings.rub_price(tariff)
    if method == "stars":
        return settings.stars_price(tariff)
    raise ValueError("unknown payment method")


def parse_price(value: str | int) -> int:
    raw = str(value).strip().replace(" ", "")
    if raw.startswith("+"):
        raw = raw[1:]
    if not raw.isdigit():
        raise ValueError("price must be an integer")
    amount = int(raw)
    if amount <= 0:
        raise ValueError("price must be positive")
    if amount > 10_000_000:
        raise ValueError("price is too large")
    return amount


async def get_runtime_setting(session: AsyncSession, key: str) -> Setting | None:
    return await session.scalar(select(Setting).where(Setting.key == key))


async def get_prime_price(session: AsyncSession, settings: Settings, method: str, tariff: str) -> int:
    key = price_key(method, tariff)
    item = await get_runtime_setting(session, key)
    if item:
        try:
            return parse_price(item.value)
        except ValueError:
            # Bad runtime value must never break payments. Fall back to env.
            return fallback_price(settings, method, tariff)
    return fallback_price(settings, method, tariff)


async def get_prime_prices(session: AsyncSession, settings: Settings, method: str) -> dict[str, int]:
    return {tariff: await get_prime_price(session, settings, method, tariff) for tariff in TARIFFS}


async def get_prime_price_views(session: AsyncSession, settings: Settings) -> list[PriceView]:
    keys = [price_key(method, tariff) for method in METHODS for tariff in TARIFFS]
    result = await session.scalars(select(Setting).where(Setting.key.in_(keys)))
    runtime = {item.key: item.value for item in result}

    views: list[PriceView] = []
    for method in METHODS:
        for tariff in TARIFFS:
            key = price_key(method, tariff)
            source = "env"
            amount = fallback_price(settings, method, tariff)
            if key in runtime:
                try:
                    amount = parse_price(runtime[key])
                    source = "admin"
                except ValueError:
                    source = "env / bad runtime"
            views.append(PriceView(method=method, tariff=tariff, amount=amount, key=key, source=source))
    return views


async def set_prime_price(session: AsyncSession, method: str, tariff: str, amount: str | int) -> Setting:
    key = price_key(method, tariff)
    parsed = parse_price(amount)
    item = await get_runtime_setting(session, key)
    if item:
        item.value = str(parsed)
    else:
        item = Setting(key=key, value=str(parsed))
        session.add(item)
    await session.flush()
    return item
