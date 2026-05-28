from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import User
from database.queries import get_payment_by_invoice, mark_payment_paid
from keyboards.payments import platega_pay
from keyboards.prime import prime_success
from services.payments.platega import PlategaError, create_payment_link, create_platega_payment
from services.payments.telegram_stars import create_stars_invoice, parse_stars_payload
from services.prime_access import grant_prime
from texts import PRIME_ACTIVATED, platega_invoice
from utils.telegram import safe_callback_answer, safe_edit_callback

logger = logging.getLogger(__name__)
router = Router(name="payments")


@router.callback_query(F.data.startswith("prime:tariff:"))
async def choose_tariff(
    callback: CallbackQuery,
    bot: Bot,
    session: AsyncSession,
    current_user: User,
    settings: Settings,
) -> None:
    _, _, method, tariff = callback.data.split(":")
    if method == "robokassa":
        method = "platega"
    if method == "stars":
        await create_stars_invoice(bot, session, current_user, settings, tariff)
        await safe_callback_answer(callback, "Счёт отправлен")
        return

    try:
        payment = await create_platega_payment(session, current_user, settings, tariff)
        url = await create_payment_link(settings, payment)
    except PlategaError:
        logger.exception("platega invoice creation failed")
        await session.rollback()
        await safe_callback_answer(callback, "⛔ Платёж временно недоступен", show_alert=True)
        return

    await safe_edit_callback(
        callback,
        platega_invoice(tariff, int(payment.amount)),
        reply_markup=platega_pay(url, tariff),
    )
    await safe_callback_answer(callback)


@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery, session: AsyncSession) -> None:
    parsed = parse_stars_payload(pre_checkout_query.invoice_payload)
    if not parsed:
        await pre_checkout_query.answer(ok=False, error_message="Некорректный платёж PRIME NICK")
        return
    invoice_id, _ = parsed
    payment = await get_payment_by_invoice(session, invoice_id)
    if not payment or payment.status not in {"created", "pending"}:
        await pre_checkout_query.answer(ok=False, error_message="Счёт не найден или уже закрыт")
        return
    await pre_checkout_query.answer(ok=True)


@router.message(F.successful_payment)
async def successful_stars_payment(message: Message, session: AsyncSession) -> None:
    payload = message.successful_payment.invoice_payload
    parsed = parse_stars_payload(payload)
    if not parsed:
        logger.warning("unknown successful payment payload")
        return
    invoice_id, tariff = parsed
    payment = await get_payment_by_invoice(session, invoice_id)
    if not payment:
        logger.warning("payment not found invoice_id=%s", invoice_id)
        return
    user = await payment.awaitable_attrs.user
    if payment.status != "paid":
        await mark_payment_paid(session, payment)
        grant_prime(user, tariff=tariff)
    await message.answer(PRIME_ACTIVATED, reply_markup=prime_success())
