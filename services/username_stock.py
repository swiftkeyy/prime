from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User, UsernameStock
from services.reservations import is_username_reserved
from utils.time import utcnow
from utils.validators import is_valid_username

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StockTakeResult:
    username: str | None
    reason: str = "empty"


def _matches_filters(username: str, *, digits_enabled: bool, underscore_enabled: bool) -> bool:
    if not digits_enabled and any(ch.isdigit() for ch in username):
        return False
    if not underscore_enabled and "_" in username:
        return False
    return True


async def release_expired_stock_holds(session: AsyncSession) -> int:
    now = utcnow()
    result = await session.scalars(
        select(UsernameStock).where(
            UsernameStock.status == "issued",
            UsernameStock.issued_until.is_not(None),
            UsernameStock.issued_until < now,
            UsernameStock.expires_at > now,
        ).limit(100)
    )
    items = list(result)
    for item in items:
        item.status = "available"
        item.issued_to_user_id = None
        item.issued_until = None
    if items:
        await session.flush()
    return len(items)


async def count_available_stock(session: AsyncSession, length: int) -> int:
    now = utcnow()
    return int(
        await session.scalar(
            select(func.count(UsernameStock.id)).where(
                UsernameStock.length == length,
                UsernameStock.status == "available",
                UsernameStock.expires_at > now,
            )
        )
        or 0
    )


async def take_available_username(
    session: AsyncSession,
    user: User,
    length: int,
    *,
    settings: Settings,
    digits_enabled: bool,
    underscore_enabled: bool,
    seed: str | None = None,
) -> StockTakeResult:
    """Atomically-ish take one pre-verified username from the local stock.

    This avoids burning Telegram MTProto requests on every user click. Items are
    held for a short time, so the same username is not shown to everyone in a row.
    Reservation remains the final user-facing lock.
    """
    await release_expired_stock_holds(session)
    now = utcnow()
    seed = (seed or "").lower().lstrip("@")

    stmt = (
        select(UsernameStock)
        .where(
            UsernameStock.length == length,
            UsernameStock.status == "available",
            UsernameStock.expires_at > now,
        )
        .order_by(UsernameStock.checked_at.desc(), UsernameStock.id.asc())
        .limit(80)
    )
    rows = list(await session.scalars(stmt))
    if seed:
        rows = [row for row in rows if seed in row.username]

    for row in rows:
        username = row.username.lower().lstrip("@")
        if not is_valid_username(username):
            row.status = "rejected"
            continue
        if not _matches_filters(username, digits_enabled=digits_enabled, underscore_enabled=underscore_enabled):
            continue
        if await is_username_reserved(session, username):
            row.status = "reserved"
            continue

        row.status = "issued"
        row.issued_to_user_id = user.id
        row.issued_until = now + timedelta(minutes=max(1, settings.USERNAME_STOCK_HOLD_MINUTES))
        await session.flush()
        return StockTakeResult(username=username, reason="ok")

    await session.flush()
    return StockTakeResult(username=None, reason="empty")


async def upsert_available_username(
    session: AsyncSession,
    username: str,
    *,
    settings: Settings,
    source: str = "worker",
) -> None:
    username = username.lower().lstrip("@")
    if not is_valid_username(username):
        return

    now = utcnow()
    expires_at = now + timedelta(hours=max(1, settings.USERNAME_STOCK_TTL_HOURS))
    item = await session.scalar(select(UsernameStock).where(UsernameStock.username == username))
    if item is None:
        session.add(
            UsernameStock(
                username=username,
                length=len(username),
                status="available",
                source=source,
                checked_at=now,
                expires_at=expires_at,
            )
        )
    else:
        item.length = len(username)
        item.status = "available"
        item.source = source
        item.checked_at = now
        item.expires_at = expires_at
        item.issued_to_user_id = None
        item.issued_until = None
    await session.flush()


async def mark_username_rejected(session: AsyncSession, username: str, *, source: str = "worker") -> None:
    username = username.lower().lstrip("@")
    if not username:
        return
    item = await session.scalar(select(UsernameStock).where(UsernameStock.username == username))
    now = utcnow()
    if item is None:
        session.add(
            UsernameStock(
                username=username,
                length=len(username),
                status="rejected",
                source=source,
                checked_at=now,
                expires_at=now,
            )
        )
    else:
        item.status = "rejected"
        item.source = source
        item.checked_at = now
        item.expires_at = now
        item.issued_to_user_id = None
        item.issued_until = None
    await session.flush()
