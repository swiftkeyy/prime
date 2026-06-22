from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from database.queries import get_payment_by_invoice, mark_payment_paid
from keyboards.prime import prime_success
from services.payments.platega import is_confirmed_status, is_failed_status, verify_callback_headers
from services.prime_access import grant_prime
from texts import PLATEGA_SUCCESS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/platega")


@router.post("/callback", response_class=PlainTextResponse)
async def platega_callback(request: Request) -> str:
    settings = request.app.state.settings
    merchant_id = request.headers.get("X-MerchantId")
    secret = request.headers.get("X-Secret")
    if not verify_callback_headers(settings, merchant_id, secret):
        logger.warning("platega callback invalid headers merchant=%s", merchant_id)
        raise HTTPException(status_code=403, detail="invalid callback headers")

    data = await request.json()
    transaction_id = str(data.get("id") or data.get("transactionId") or "").strip()
    status = str(data.get("status") or "").upper()
    currency = str(data.get("currency") or "").upper()
    amount_raw = data.get("amount")

    if not transaction_id or not status:
        raise HTTPException(status_code=400, detail="missing callback params")

    async with request.app.state.sessionmaker() as session:
        payment = await get_payment_by_invoice(session, transaction_id)
        if not payment:
            logger.warning("platega callback payment not found transaction=%s", transaction_id)
            raise HTTPException(status_code=404, detail="payment not found")

        if currency and currency != payment.currency.upper():
            logger.warning("platega currency mismatch transaction=%s currency=%s", transaction_id, currency)
            raise HTTPException(status_code=400, detail="currency mismatch")

        if amount_raw is not None:
            try:
                callback_amount = Decimal(str(amount_raw)).quantize(Decimal("0.01"))
                expected_amount = Decimal(str(payment.amount)).quantize(Decimal("0.01"))
                if callback_amount != expected_amount:
                    logger.warning("platega amount mismatch transaction=%s got=%s expected=%s", transaction_id, callback_amount, expected_amount)
            except (InvalidOperation, ValueError):
                logger.warning("platega invalid amount in callback transaction=%s amount_raw=%s", transaction_id, amount_raw)

        user = await payment.awaitable_attrs.user
        if is_confirmed_status(status):
            if payment.status != "paid":
                await mark_payment_paid(session, payment)
                grant_prime(user, tariff=payment.tariff)
                await session.commit()
                try:
                    await request.app.state.bot.send_message(user.telegram_id, PLATEGA_SUCCESS, reply_markup=prime_success())
                except Exception as exc:  # noqa: BLE001
                    logger.info("could not notify platega paid user transaction=%s: %s", transaction_id, exc.__class__.__name__)
            else:
                await session.rollback()
            return "OK"

        if is_failed_status(status):
            if payment.status != "paid":
                payment.status = "failed" if status != "CANCELED" else "cancelled"
                await session.commit()
            else:
                await session.rollback()
            return "OK"

        payment.status = "pending"
        await session.commit()
    return "OK"


@router.get("/success", response_class=HTMLResponse)
async def platega_success() -> str:
    return """
    <html><body style='font-family:Inter,Arial,sans-serif;background:#0b0f1a;color:#f5f7ff;padding:32px'>
    <h1>✅ Оплата обрабатывается</h1>
    <p>Вернитесь в Telegram. PRIME PASS активируется после callback-подтверждения Platega.</p>
    </body></html>
    """


@router.get("/fail", response_class=HTMLResponse)
async def platega_fail() -> str:
    return """
    <html><body style='font-family:Inter,Arial,sans-serif;background:#0b0f1a;color:#f5f7ff;padding:32px'>
    <h1>⛔ Оплата не завершена</h1>
    <p>Вернитесь в Telegram и попробуйте ещё раз.</p>
    </body></html>
    """
