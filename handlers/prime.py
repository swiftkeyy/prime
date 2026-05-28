from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Settings
from sqlalchemy.ext.asyncio import AsyncSession
from keyboards.prime import prime_menu as prime_kb, tariffs
from services.pricing import get_prime_prices
from texts import PRIME_MENU, TARIFFS_HEADER
from utils.telegram import safe_callback_answer, safe_edit_callback

router = Router(name="prime")


@router.callback_query(F.data == "prime:menu")
async def prime_menu(callback: CallbackQuery) -> None:
    await safe_edit_callback(callback, PRIME_MENU, reply_markup=prime_kb())
    await safe_callback_answer(callback)


@router.callback_query(F.data == "prime:stars")
async def stars_tariffs(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    prices = await get_prime_prices(session, settings, "stars")
    await safe_edit_callback(callback, TARIFFS_HEADER, reply_markup=tariffs("stars", prices, "⭐"))
    await safe_callback_answer(callback)


@router.callback_query(F.data.in_({"prime:platega", "prime:robokassa"}))
async def platega_tariffs(callback: CallbackQuery, session: AsyncSession, settings: Settings) -> None:
    prices = await get_prime_prices(session, settings, "platega")
    await safe_edit_callback(callback, TARIFFS_HEADER, reply_markup=tariffs("platega", prices, "₽"))
    await safe_callback_answer(callback)
