from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import ReferralEvent, User
from database.queries import (
    count_referrals_by_inviter,
    get_referral_event_for_referred,
    get_user_by_referral_payload,
)
from texts import REFERRAL_BONUS
from utils.referrals import normalize_referral_payload

logger = logging.getLogger(__name__)


async def process_referral(
    session: AsyncSession,
    bot: Bot,
    new_user: User,
    start_payload: str | None,
    is_new_user: bool,
    settings: Settings,
) -> bool:
    """Attach a new user to an inviter and issue the referral bonus once.

    Rules:
    - referral is credited only for a new user;
    - self-invite is ignored;
    - one referred user can be credited only once;
    - old numeric links and new ref_<code> links are both supported.
    """
    payload = normalize_referral_payload(start_payload)
    if not is_new_user or not payload:
        return False

    if new_user.invited_by is not None:
        return False

    inviter = await get_user_by_referral_payload(session, payload)
    if not inviter:
        logger.info("referral skipped: inviter not found payload=%s user=%s", payload, new_user.telegram_id)
        return False

    if inviter.id == new_user.id or inviter.telegram_id == new_user.telegram_id:
        logger.info("referral skipped: self invite user=%s", new_user.telegram_id)
        return False

    existing_event = await get_referral_event_for_referred(session, new_user.id)
    if existing_event is not None:
        return False

    bonus = max(0, int(settings.REFERRAL_BONUS_ATTEMPTS))

    new_user.invited_by = inviter.id
    inviter.bonus_attempts += bonus
    inviter.referrals_count = max(
        inviter.referrals_count + 1,
        (await count_referrals_by_inviter(session, inviter.id)) + 1,
    )

    session.add(
        ReferralEvent(
            inviter_id=inviter.id,
            referred_user_id=new_user.id,
            bonus_attempts=bonus,
        )
    )

    # The migration adds a unique constraint on referred_user_id, so even in a race
    # PostgreSQL will not allow double-crediting one invited user.
    await session.flush()

    try:
        await bot.send_message(inviter.telegram_id, REFERRAL_BONUS.format(bonus=bonus))
    except Exception as exc:  # noqa: BLE001
        logger.info("could not notify inviter %s: %s", inviter.telegram_id, exc.__class__.__name__)

    logger.info(
        "referral credited inviter=%s referred=%s bonus=%s",
        inviter.telegram_id,
        new_user.telegram_id,
        bonus,
    )
    return True
