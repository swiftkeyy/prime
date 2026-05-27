from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Settings
from keyboards.prime import prime_menu as prime_kb, tariffs
from texts import PRIME_MENU, TARIFFS_HEADER

router = Router(name="prime")


@router.callback_query(F.data == "prime:menu")
async def prime_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(PRIME_MENU, reply_markup=prime_kb())
    await callback.answer()


@router.callback_query(F.data == "prime:stars")
async def stars_tariffs(callback: CallbackQuery, settings: Settings) -> None:
    prices = {t: settings.stars_price(t) for t in ("1d", "7d", "30d", "forever")}
    await callback.message.edit_text(TARIFFS_HEADER, reply_markup=tariffs("stars", prices, "⭐"))
    await callback.answer()


@router.callback_query(F.data == "prime:robokassa")
async def robokassa_tariffs(callback: CallbackQuery, settings: Settings) -> None:
    prices = {t: settings.rub_price(t) for t in ("1d", "7d", "30d", "forever")}
    await callback.message.edit_text(TARIFFS_HEADER, reply_markup=tariffs("robokassa", prices, "₽"))
    await callback.answer()
