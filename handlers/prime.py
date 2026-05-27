from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Settings
from sqlalchemy.ext.asyncio import AsyncSession
from keyboards.prime import prime_menu as prime_kb, tariffs
from services.pricing import get_prime_prices
from texts import PRIME_MENU, TARIFFS_HEADER

router = Router(name="prime")


@router.callback_query(F.data == "prime:menu")
async def prime_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(PRIME_MENU, reply_markup=prime_kb())
    await callback.answer()


@router.callback_query(F.data == "prime:stars")
async def stars_tariffs(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    prices = await get_prime_prices(session, settings, "stars")
    await callback.message.edit_text(TARIFFS_HEADER, reply_markup=tariffs("stars", prices, "⭐"))
    await callback.answer()


@router.callback_query(F.data == "prime:robokassa")
async def robokassa_tariffs(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    prices = await get_prime_prices(session, settings, "robokassa")
    await callback.message.edit_text(TARIFFS_HEADER, reply_markup=tariffs("robokassa", prices, "₽"))
    await callback.answer()
