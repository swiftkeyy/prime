from __future__ import annotations

from datetime import datetime, timedelta

from database.models import User
from utils.formatters import tariff_days
from utils.time import utcnow

FOREVER_UNTIL = datetime(2999, 12, 31, 23, 59, 59, tzinfo=utcnow().tzinfo)


def is_prime_active(user: User) -> bool:
    if not user.is_prime:
        return False
    if user.prime_until is None:
        return True
    if user.prime_until >= utcnow():
        return True
    user.is_prime = False
    return False


def grant_prime(user: User, tariff: str | None = None, days: int | None = None) -> None:
    now = utcnow()
    if tariff:
        days = tariff_days(tariff)
    user.is_prime = True
    if days is None:
        user.prime_until = FOREVER_UNTIL
        return
    base = user.prime_until if user.prime_until and user.prime_until > now else now
    user.prime_until = base + timedelta(days=days)


def revoke_prime(user: User) -> None:
    user.is_prime = False
    user.prime_until = None
