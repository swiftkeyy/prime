from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Settings
from database.models import User
from keyboards.profile import profile_menu
from services.attempts import attempts_reset_left, total_attempts
from services.prime_access import is_prime_active
from texts import profile

router = Router(name="profile")


@router.callback_query(F.data == "profile:open")
async def open_profile(callback: CallbackQuery, current_user: User, settings: Settings) -> None:
    is_prime_active(current_user)
    link = f"https://t.me/{settings.BOT_USERNAME}?start={current_user.telegram_id}"
    await callback.message.edit_text(
        profile(current_user, settings, attempts_reset_left(current_user, settings), total_attempts(current_user, settings)),
        reply_markup=profile_menu(link),
    )
    await callback.answer()
