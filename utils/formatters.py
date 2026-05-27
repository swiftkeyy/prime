from __future__ import annotations

from html import escape
from decimal import Decimal


def h(value: object) -> str:
    return escape(str(value), quote=False)


def money_rub(value: Decimal | int | str) -> str:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    if value == value.to_integral():
        return f"{int(value)} ₽"
    return f"{value:.2f} ₽"


def tariff_title(tariff: str) -> str:
    return {
        "1d": "24 часа",
        "7d": "7 дней",
        "30d": "30 дней",
        "forever": "навсегда",
    }.get(tariff, tariff)


def tariff_days(tariff: str) -> int | None:
    return {
        "1d": 1,
        "7d": 7,
        "30d": 30,
        "forever": None,
    }[tariff]
