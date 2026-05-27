from __future__ import annotations

from datetime import timedelta

from config import Settings
from database.models import User
from services.prime_access import is_prime_active
from utils.time import human_time_left, utcnow


def refresh_attempts_if_needed(user: User, settings: Settings) -> None:
    now = utcnow()
    if user.last_attempts_reset is None:
        user.last_attempts_reset = now
        user.attempts_left = max(user.attempts_left, settings.FREE_ATTEMPTS)
        return
    cooldown = timedelta(hours=settings.ATTEMPTS_COOLDOWN_HOURS)
    if now - user.last_attempts_reset >= cooldown:
        user.attempts_left = settings.FREE_ATTEMPTS
        user.last_attempts_reset = now


def total_attempts(user: User, settings: Settings) -> int:
    refresh_attempts_if_needed(user, settings)
    if is_prime_active(user):
        return 999_999
    return max(0, user.attempts_left) + max(0, user.bonus_attempts)


def can_search(user: User, settings: Settings) -> bool:
    return is_prime_active(user) or total_attempts(user, settings) > 0


def consume_attempt(user: User, settings: Settings) -> None:
    refresh_attempts_if_needed(user, settings)
    if is_prime_active(user):
        return
    if user.bonus_attempts > 0:
        user.bonus_attempts -= 1
        return
    if user.attempts_left > 0:
        user.attempts_left -= 1


def attempts_reset_left(user: User, settings: Settings) -> str:
    if is_prime_active(user):
        return "без ожидания"
    now = utcnow()
    if user.last_attempts_reset is None:
        return "сейчас"
    next_reset = user.last_attempts_reset + timedelta(hours=settings.ATTEMPTS_COOLDOWN_HOURS)
    return human_time_left(next_reset - now)
