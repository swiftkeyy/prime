from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from aiogram.types import User as TgUser
from sqlalchemy import Select, and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Payment, PromoActivation, PromoCode, ReferralEvent, Search, User, UsernameStock
from utils.time import utcnow


async def get_user_by_tg_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))




async def get_user_by_referral_code(session: AsyncSession, referral_code: str) -> User | None:
    code = referral_code.strip()
    if not code:
        return None
    return await session.scalar(select(User).where(func.lower(User.referral_code) == code.lower()))


async def get_user_by_referral_payload(session: AsyncSession, payload: str) -> User | None:
    value = payload.strip().lstrip("@")
    if not value:
        return None

    # Backward compatibility: old links used telegram_id directly.
    if value.isdigit():
        user = await get_user_by_tg_id(session, int(value))
        if user:
            return user

    return await get_user_by_referral_code(session, value)


async def get_referral_event_for_referred(session: AsyncSession, referred_user_id: int) -> ReferralEvent | None:
    return await session.scalar(
        select(ReferralEvent).where(ReferralEvent.referred_user_id == referred_user_id)
    )


async def count_referrals_by_inviter(session: AsyncSession, inviter_id: int) -> int:
    return int(
        await session.scalar(select(func.count(ReferralEvent.id)).where(ReferralEvent.inviter_id == inviter_id)) or 0
    )


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
        if not user.referral_code:
            user.referral_code = str(tg_user.id)
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


async def best_user_searches(session: AsyncSession, user: User, limit: int = 8) -> list[Search]:
    result = await session.scalars(
        select(Search)
        .where(Search.user_id == user.id, Search.username_result.is_not(None))
        .order_by(Search.created_at.desc(), Search.id.desc())
        .limit(limit)
    )
    return list(result)


async def admin_stock_snapshot(session: AsyncSession) -> dict[str, int]:
    now = utcnow()
    result = await session.scalars(
        select(UsernameStock).where(UsernameStock.expires_at > now)
    )
    items = list(result)
    clean_5 = mixed_5 = stock_6 = stock_7 = issued = reserved = rejected = 0
    for item in items:
        username = item.username or ""
        if item.status == "issued":
            issued += 1
        elif item.status == "reserved":
            reserved += 1
        elif item.status == "rejected":
            rejected += 1

        if item.status != "available":
            continue
        if item.length == 5:
            if any(ch.isdigit() for ch in username):
                mixed_5 += 1
            else:
                clean_5 += 1
        elif item.length == 6:
            stock_6 += 1
        elif item.length == 7:
            stock_7 += 1

    return {
        "clean_5": clean_5,
        "mixed_5": mixed_5,
        "stock_6": stock_6,
        "stock_7": stock_7,
        "issued": issued,
        "reserved": reserved,
        "rejected": rejected,
    }


async def admin_search_diagnostics(session: AsyncSession, hours: int = 24) -> dict[str, int]:
    since = utcnow() - timedelta(hours=hours)
    rows = await session.execute(
        select(Search.status, func.count(Search.id))
        .where(Search.created_at >= since)
        .group_by(Search.status)
    )
    data = {str(status): int(count) for status, count in rows.all()}
    return {
        "found": data.get("found", 0) + data.get("custom_found", 0),
        "not_found": data.get("not_found", 0) + data.get("custom_not_found", 0),
        "stock_empty": data.get("stock_empty", 0),
        "checker_rate_limited": data.get("checker_rate_limited", 0),
        "checker_error": data.get("checker_error", 0),
    }


async def admin_live_feed(session: AsyncSession, limit: int = 15) -> list[tuple[str, str, datetime]]:
    feed: list[tuple[str, str, datetime]] = []

    searches = await session.execute(
        select(User.telegram_id, Search.status, Search.username_result, Search.created_at)
        .join(User, Search.user_id == User.id)
        .order_by(Search.created_at.desc())
        .limit(limit)
    )
    for tg_id, status, username_result, created_at in searches.all():
        uname = f" @{username_result}" if username_result else ""
        feed.append(("search", f"<code>{tg_id}</code> · {status}{uname}", created_at))

    payments = await session.execute(
        select(User.telegram_id, Payment.status, Payment.method, Payment.created_at)
        .join(User, Payment.user_id == User.id)
        .order_by(Payment.created_at.desc())
        .limit(limit)
    )
    for tg_id, status, method, created_at in payments.all():
        feed.append(("payment", f"<code>{tg_id}</code> · {status} · {method}", created_at))

    referrals = await session.execute(
        select(ReferralEvent.inviter_id, ReferralEvent.referred_user_id, ReferralEvent.created_at)
        .order_by(ReferralEvent.created_at.desc())
        .limit(limit)
    )
    for inviter_id, referred_user_id, created_at in referrals.all():
        feed.append(("referral", f"inviter={inviter_id} -> referred={referred_user_id}", created_at))

    feed.sort(key=lambda item: item[2], reverse=True)
    return feed[:limit]


async def admin_growth_lab(session: AsyncSession) -> dict[str, Any]:
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    today_paid = await session.scalar(select(func.count(Payment.id)).where(Payment.status == "paid", Payment.created_at >= day_start)) or 0
    week_paid = await session.scalar(select(func.count(Payment.id)).where(Payment.status == "paid", Payment.created_at >= week_start)) or 0
    today_refs = await session.scalar(select(func.count(ReferralEvent.id)).where(ReferralEvent.created_at >= day_start)) or 0
    week_refs = await session.scalar(select(func.count(ReferralEvent.id)).where(ReferralEvent.created_at >= week_start)) or 0
    prime_users = await session.scalar(select(func.count(User.id)).where(User.is_prime.is_(True), User.prime_until >= now)) or 0
    users_total = await session.scalar(select(func.count(User.id))) or 0
    return {
        "today_paid": int(today_paid),
        "week_paid": int(week_paid),
        "today_refs": int(today_refs),
        "week_refs": int(week_refs),
        "prime_users": int(prime_users),
        "users_total": int(users_total),
    }


async def admin_recent_referrals(session: AsyncSession, limit: int = 12) -> list[ReferralEvent]:
    result = await session.scalars(select(ReferralEvent).order_by(ReferralEvent.created_at.desc()).limit(limit))
    return list(result)
# ─────────────────────────────────────────────────────────────────────────────
# Admin center queries
# ─────────────────────────────────────────────────────────────────────────────

async def admin_dashboard(session: AsyncSession) -> dict[str, Any]:
    now = utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    users_total = await session.scalar(select(func.count(User.id))) or 0
    users_today = await session.scalar(select(func.count(User.id)).where(User.created_at >= day_start)) or 0
    users_week = await session.scalar(select(func.count(User.id)).where(User.created_at >= week_start)) or 0
    prime_active = await session.scalar(
        select(func.count(User.id)).where(User.is_prime.is_(True), User.prime_until >= now)
    ) or 0
    prime_expired_flagged = await session.scalar(
        select(func.count(User.id)).where(User.is_prime.is_(True), User.prime_until < now)
    ) or 0

    searches_total = await session.scalar(select(func.count(Search.id))) or 0
    searches_today = await session.scalar(select(func.count(Search.id)).where(Search.created_at >= day_start)) or 0
    searches_week = await session.scalar(select(func.count(Search.id)).where(Search.created_at >= week_start)) or 0
    found_total = await session.scalar(select(func.count(Search.id)).where(Search.status == "found")) or 0
    not_found_total = await session.scalar(select(func.count(Search.id)).where(Search.status != "found")) or 0

    payments_paid = await session.scalar(select(func.count(Payment.id)).where(Payment.status == "paid")) or 0
    payments_pending = await session.scalar(select(func.count(Payment.id)).where(Payment.status.in_(["created", "pending"]))) or 0
    rub_revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid", Payment.currency == "RUB")
    ) or Decimal("0")
    stars_revenue = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid", Payment.currency == "XTR")
    ) or Decimal("0")

    active_promos = await session.scalar(select(func.count(PromoCode.id)).where(PromoCode.is_active.is_(True))) or 0
    promo_activations = await session.scalar(select(func.count(PromoActivation.id))) or 0
    referrals_total = await session.scalar(select(func.coalesce(func.sum(User.referrals_count), 0))) or 0

    return {
        "users_total": users_total,
        "users_today": users_today,
        "users_week": users_week,
        "prime_active": prime_active,
        "prime_expired_flagged": prime_expired_flagged,
        "base_users": max(0, users_total - prime_active),
        "searches_total": searches_total,
        "searches_today": searches_today,
        "searches_week": searches_week,
        "found_total": found_total,
        "not_found_total": not_found_total,
        "payments_paid": payments_paid,
        "payments_pending": payments_pending,
        "rub_revenue": rub_revenue,
        "stars_revenue": stars_revenue,
        "active_promos": active_promos,
        "promo_activations": promo_activations,
        "referrals_total": referrals_total,
    }


async def admin_users_page(session: AsyncSession, mode: str = "latest", page: int = 0, limit: int = 8) -> tuple[list[User], int]:
    now = utcnow()
    page = max(0, page)
    offset = page * limit
    stmt = select(User)
    count_stmt = select(func.count(User.id))

    if mode == "prime":
        stmt = stmt.where(User.is_prime.is_(True), User.prime_until >= now).order_by(User.prime_until.desc(), User.id.desc())
        count_stmt = count_stmt.where(User.is_prime.is_(True), User.prime_until >= now)
    elif mode == "top_searches":
        stmt = stmt.order_by(User.total_searches.desc(), User.id.desc())
    elif mode == "top_refs":
        stmt = stmt.order_by(User.referrals_count.desc(), User.id.desc())
    else:
        stmt = stmt.order_by(User.created_at.desc(), User.id.desc())

    total = await session.scalar(count_stmt) or 0
    result = await session.scalars(stmt.offset(offset).limit(limit))
    return list(result), int(total)


async def admin_recent_searches(session: AsyncSession, limit: int = 12) -> list[tuple[Search, int | None]]:
    stmt = (
        select(Search, User.telegram_id)
        .join(User, Search.user_id == User.id)
        .order_by(Search.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def admin_user_searches(session: AsyncSession, user: User, limit: int = 10) -> list[Search]:
    result = await session.scalars(
        select(Search).where(Search.user_id == user.id).order_by(Search.created_at.desc()).limit(limit)
    )
    return list(result)


async def admin_user_payments(session: AsyncSession, user: User, limit: int = 10) -> list[Payment]:
    result = await session.scalars(
        select(Payment).where(Payment.user_id == user.id).order_by(Payment.created_at.desc()).limit(limit)
    )
    return list(result)


async def admin_recent_payments(session: AsyncSession, status: str = "all", limit: int = 12) -> list[tuple[Payment, int | None]]:
    stmt = select(Payment, User.telegram_id).join(User, Payment.user_id == User.id)
    if status != "all":
        stmt = stmt.where(Payment.status == status)
    stmt = stmt.order_by(Payment.created_at.desc()).limit(limit)
    result = await session.execute(stmt)
    return [(row[0], row[1]) for row in result.all()]


async def admin_target_user_ids(session: AsyncSession, audience: str = "all") -> list[int]:
    now = utcnow()
    stmt = select(User.telegram_id).order_by(User.id.asc())
    if audience == "prime":
        stmt = stmt.where(User.is_prime.is_(True), User.prime_until >= now)
    elif audience == "base":
        stmt = stmt.where((User.is_prime.is_(False)) | (User.prime_until < now))
    result = await session.scalars(stmt)
    return list(result)


async def admin_promos_page(session: AsyncSession, active_only: bool = True, limit: int = 12) -> list[PromoCode]:
    stmt = select(PromoCode).order_by(PromoCode.created_at.desc()).limit(limit)
    if active_only:
        stmt = stmt.where(PromoCode.is_active.is_(True))
    result = await session.scalars(stmt)
    return list(result)


async def admin_get_promo_by_id(session: AsyncSession, promo_id: int) -> PromoCode | None:
    return await session.get(PromoCode, promo_id)


async def admin_deactivate_promo(session: AsyncSession, promo_id: int) -> PromoCode | None:
    promo = await admin_get_promo_by_id(session, promo_id)
    if promo:
        promo.is_active = False
        await session.flush()
    return promo


async def admin_settings_list(session: AsyncSession, limit: int = 30) -> list[Setting]:
    from database.models import Setting

    result = await session.scalars(select(Setting).order_by(Setting.key.asc()).limit(limit))
    return list(result)


async def admin_upsert_setting(session: AsyncSession, key: str, value: str) -> Setting:
    from database.models import Setting

    key = key.strip()
    item = await session.scalar(select(Setting).where(Setting.key == key))
    if item:
        item.value = value
    else:
        item = Setting(key=key, value=value)
        session.add(item)
    await session.flush()
    return item
