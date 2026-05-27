from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def add_days(base: datetime, days: int) -> datetime:
    return base + timedelta(days=days)


def human_time_left(delta: timedelta) -> str:
    seconds = max(0, int(delta.total_seconds()))
    hours, rem = divmod(seconds, 3600)
    minutes, _ = divmod(rem, 60)
    if hours <= 0:
        return f"{minutes} мин."
    return f"{hours} ч. {minutes} мин."


def format_dt(dt: datetime | None) -> str:
    if not dt:
        return "не активен"
    return dt.astimezone(UTC).strftime("%d.%m.%Y %H:%M UTC")
