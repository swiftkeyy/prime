from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from keyboards.main import back_home
from services.promo_codes import PromoActivationError, activate_promo
from texts import PROMO_ERROR, PROMO_START, promo_success

router = Router(name="promo")


class PromoState(StatesGroup):
    waiting_code = State()


@router.callback_query(F.data == "promo:start")
async def promo_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(PromoState.waiting_code)
    await callback.message.edit_text(PROMO_START, reply_markup=back_home())
    await callback.answer()


@router.message(PromoState.waiting_code)
async def promo_code(message: Message, state: FSMContext, session: AsyncSession, current_user: User) -> None:
    try:
        days = await activate_promo(session, current_user, message.text or "")
    except PromoActivationError:
        await message.answer(PROMO_ERROR, reply_markup=back_home())
        return
    await state.clear()
    await message.answer(promo_success(days), reply_markup=back_home())
