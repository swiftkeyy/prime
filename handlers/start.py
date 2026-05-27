from __future__ import annotations

from aiogram import Bot, Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from keyboards.main import main_menu
from services.referrals import process_referral
from texts import WELCOME

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    bot: Bot,
    session: AsyncSession,
    current_user: User,
    is_new_user: bool,
    start_payload: str | None,
    settings: Settings,
) -> None:
    await process_referral(session, bot, current_user, start_payload, is_new_user, settings)
    await message.answer(WELCOME, reply_markup=main_menu())
