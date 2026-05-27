from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.queries import add_promo_activation, get_promo_code, has_promo_activation
from services.prime_access import grant_prime
from utils.time import utcnow
from utils.validators import is_valid_promo, normalize_promo


class PromoActivationError(RuntimeError):
    pass


async def activate_promo(session: AsyncSession, user: User, raw_code: str) -> int:
    code = normalize_promo(raw_code)
    if not is_valid_promo(code):
        raise PromoActivationError("invalid code")

    promo = await get_promo_code(session, code)
    if not promo or not promo.is_active:
        raise PromoActivationError("not found")
    if promo.expires_at and promo.expires_at < utcnow():
        raise PromoActivationError("expired")
    if promo.used_count >= promo.max_uses:
        raise PromoActivationError("limit")
    if await has_promo_activation(session, user.id, promo.id):
        raise PromoActivationError("already used")

    grant_prime(user, days=promo.prime_days)
    promo.used_count += 1
    await add_promo_activation(session, user.id, promo.id)
    await session.flush()
    return promo.prime_days
