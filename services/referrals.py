from __future__ import annotations

import logging

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import get_user_by_tg_id
from texts import REFERRAL_BONUS

logger = logging.getLogger(__name__)


async def process_referral(
    session: AsyncSession,
    bot: Bot,
    new_user: User,
    start_payload: str | None,
    is_new_user: bool,
    settings: Settings,
) -> None:
    if not is_new_user or not start_payload or not start_payload.isdigit():
        return
    inviter_tg_id = int(start_payload)
    if inviter_tg_id == new_user.telegram_id:
        return
    inviter = await get_user_by_tg_id(session, inviter_tg_id)
    if not inviter or new_user.invited_by is not None:
        return

    new_user.invited_by = inviter.id
    inviter.referrals_count += 1
    inviter.bonus_attempts += settings.REFERRAL_BONUS_ATTEMPTS
    await session.flush()

    try:
        await bot.send_message(
            inviter.telegram_id,
            REFERRAL_BONUS.format(bonus=settings.REFERRAL_BONUS_ATTEMPTS),
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("could not notify inviter %s: %s", inviter.telegram_id, exc.__class__.__name__)
