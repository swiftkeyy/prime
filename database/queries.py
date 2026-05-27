from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from aiogram.types import User as TgUser
from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Payment, PromoActivation, PromoCode, Search, User
from utils.time import utcnow


async def get_user_by_tg_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    username = username.strip().lstrip("@")
    return await session.scalar(select(User).where(func.lower(User.username) == username.lower()))


async def get_user_by_id_or_username(session: AsyncSession, query: str) -> User | None:
    query = query.strip()
    if query.isdigit():
        return await get_user_by_tg_id(session, int(query))
    return await get_user_by_username(session, query)


async def get_or_create_user(session: AsyncSession, tg_user: TgUser, settings: Settings) -> tuple[User, bool]:
    user = await get_user_by_tg_id(session, tg_user.id)
    if user:
        user.username = tg_user.username
        user.first_name = tg_user.first_name
        return user, False

    now = utcnow()
    user = User(
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
        attempts_left=settings.FREE_ATTEMPTS,
        last_attempts_reset=now,
        referral_code=str(tg_user.id),
    )
    session.add(user)
    await session.flush()
    return user, True


async def add_search(
    session: AsyncSession,
    user: User,
    username_result: str | None,
    length: int,
    filters: dict[str, Any],
    status: str,
) -> Search:
    item = Search(
        user_id=user.id,
        username_result=username_result,
        length=length,
        filters=filters,
        status=status,
    )
    session.add(item)
    user.total_searches += 1
    await session.flush()
    return item


async def create_payment(
    session: AsyncSession,
    user: User,
    amount: Decimal | int,
    currency: str,
    method: str,
    tariff: str,
    status: str = "created",
) -> Payment:
    payment = Payment(
        user_id=user.id,
        amount=Decimal(str(amount)),
        currency=currency,
        method=method,
        status=status,
        tariff=tariff,
    )
    session.add(payment)
    await session.flush()
    payment.invoice_id = str(payment.id)
    await session.flush()
    return payment


async def get_payment_by_invoice(session: AsyncSession, invoice_id: str) -> Payment | None:
    return await session.scalar(select(Payment).where(Payment.invoice_id == str(invoice_id)))


async def mark_payment_paid(session: AsyncSession, payment: Payment) -> None:
    payment.status = "paid"
    payment.paid_at = utcnow()
    await session.flush()


async def create_promo_code(
    session: AsyncSession,
    code: str,
    prime_days: int,
    max_uses: int,
    expires_at: datetime | None,
) -> PromoCode:
    promo = PromoCode(code=code.upper(), prime_days=prime_days, max_uses=max_uses, expires_at=expires_at, is_active=True)
    session.add(promo)
    await session.flush()
    return promo


async def get_promo_code(session: AsyncSession, code: str) -> PromoCode | None:
    return await session.scalar(select(PromoCode).where(func.lower(PromoCode.code) == code.lower()))


async def has_promo_activation(session: AsyncSession, user_id: int, promo_code_id: int) -> bool:
    stmt = select(PromoActivation.id).where(
        and_(PromoActivation.user_id == user_id, PromoActivation.promo_code_id == promo_code_id)
    )
    return (await session.scalar(stmt)) is not None


async def add_promo_activation(session: AsyncSession, user_id: int, promo_code_id: int) -> None:
    session.add(PromoActivation(user_id=user_id, promo_code_id=promo_code_id))
    await session.flush()


async def stats_overview(session: AsyncSession) -> dict[str, Any]:
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    users_count = await session.scalar(select(func.count(User.id))) or 0
    prime_count = await session.scalar(select(func.count(User.id)).where(User.is_prime.is_(True))) or 0
    searches_count = await session.scalar(select(func.count(Search.id))) or 0
    today_searches = await session.scalar(select(func.count(Search.id)).where(Search.created_at >= day_start)) or 0
    payments_count = await session.scalar(select(func.count(Payment.id)).where(Payment.status == "paid")) or 0
    revenue = await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid", Payment.currency == "RUB")) or Decimal("0")
    today_users = await session.scalar(select(func.count(User.id)).where(User.created_at >= day_start)) or 0
    return {
        "users_count": users_count,
        "prime_count": prime_count,
        "searches_count": searches_count,
        "today_searches": today_searches,
        "payments_count": payments_count,
        "revenue": revenue,
        "today_users": today_users,
    }


async def recent_payments(session: AsyncSession, limit: int = 10) -> list[Payment]:
    result = await session.scalars(select(Payment).order_by(Payment.created_at.desc()).limit(limit))
    return list(result)


async def all_user_telegram_ids(session: AsyncSession) -> list[int]:
    result = await session.scalars(select(User.telegram_id).order_by(User.id.asc()))
    return list(result)
