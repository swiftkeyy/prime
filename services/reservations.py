from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import ReservedUsername, User
from services.prime_access import is_prime_active
from utils.time import utcnow
from utils.validators import normalize_username

ReserveStatus = Literal["reserved", "already_own", "taken", "limit"]


@dataclass(slots=True)
class ReserveResult:
    status: ReserveStatus
    reservation: ReservedUsername | None
    used: int
    limit: int


def reservation_limit(user: User, settings: Settings) -> int:
    return settings.PRIME_RESERVED_USERNAMES_LIMIT if is_prime_active(user) else settings.FREE_RESERVED_USERNAMES_LIMIT


async def count_active_reservations(session: AsyncSession, user: User) -> int:
    return int(
        await session.scalar(
            select(func.count(ReservedUsername.id)).where(
                ReservedUsername.user_id == user.id,
                ReservedUsername.is_active.is_(True),
            )
        )
        or 0
    )


async def get_active_reservation_by_username(session: AsyncSession, username: str) -> ReservedUsername | None:
    username = normalize_username(username)
    return await session.scalar(
        select(ReservedUsername).where(
            func.lower(ReservedUsername.username) == username.lower(),
            ReservedUsername.is_active.is_(True),
        )
    )


async def is_username_reserved(session: AsyncSession, username: str) -> bool:
    return (await get_active_reservation_by_username(session, username)) is not None


async def user_active_reservations(session: AsyncSession, user: User) -> list[ReservedUsername]:
    result = await session.scalars(
        select(ReservedUsername)
        .where(ReservedUsername.user_id == user.id, ReservedUsername.is_active.is_(True))
        .order_by(ReservedUsername.created_at.desc(), ReservedUsername.id.desc())
    )
    return list(result)


async def get_user_reservation_by_id(session: AsyncSession, user: User, reservation_id: int) -> ReservedUsername | None:
    return await session.scalar(
        select(ReservedUsername).where(
            ReservedUsername.id == reservation_id,
            ReservedUsername.user_id == user.id,
            ReservedUsername.is_active.is_(True),
        )
    )


async def reserve_username(
    session: AsyncSession,
    user: User,
    username: str,
    settings: Settings,
    source_search_id: int | None = None,
) -> ReserveResult:
    username = normalize_username(username)
    limit = reservation_limit(user, settings)
    used = await count_active_reservations(session, user)

    existing = await get_active_reservation_by_username(session, username)
    if existing:
        if existing.user_id == user.id:
            return ReserveResult("already_own", existing, used, limit)
        return ReserveResult("taken", existing, used, limit)

    if used >= limit:
        return ReserveResult("limit", None, used, limit)

    item = ReservedUsername(
        user_id=user.id,
        username=username.lower(),
        length=len(username),
        source_search_id=source_search_id,
        is_active=True,
    )
    session.add(item)
    await session.flush()
    return ReserveResult("reserved", item, used + 1, limit)


async def release_reservation(session: AsyncSession, reservation: ReservedUsername) -> None:
    reservation.is_active = False
    reservation.released_at = utcnow()
    await session.flush()
