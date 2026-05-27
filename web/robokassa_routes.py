from __future__ import annotations

import logging
from decimal import Decimal
from urllib.parse import parse_qs

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from database.queries import get_payment_by_invoice, mark_payment_paid
from keyboards.prime import prime_success
from services.payments.robokassa import format_out_sum, verify_result_signature
from services.prime_access import grant_prime
from texts import ROBOKASSA_SUCCESS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/robokassa")


async def read_params(request: Request) -> dict[str, str]:
    params = dict(request.query_params)
    body = await request.body()
    if body:
        parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
        params.update({k: v[-1] for k, v in parsed.items()})
    return params


@router.post("/result", response_class=PlainTextResponse)
async def robokassa_result(request: Request) -> str:
    settings = request.app.state.settings
    params = await read_params(request)
    out_sum = params.get("OutSum", "")
    inv_id = params.get("InvId", "")
    signature = params.get("SignatureValue", "")

    if not out_sum or not inv_id or not signature:
        raise HTTPException(status_code=400, detail="missing payment params")
    if not verify_result_signature(settings, out_sum, inv_id, signature):
        logger.warning("robokassa invalid signature invoice=%s", inv_id)
        raise HTTPException(status_code=403, detail="invalid signature")

    async with request.app.state.sessionmaker() as session:
        payment = await get_payment_by_invoice(session, inv_id)
        if not payment:
            raise HTTPException(status_code=404, detail="payment not found")
        expected_sum = format_out_sum(payment.amount)
        if Decimal(out_sum) != Decimal(expected_sum):
            logger.warning("robokassa amount mismatch invoice=%s", inv_id)
            raise HTTPException(status_code=400, detail="amount mismatch")
        user = await payment.awaitable_attrs.user
        if payment.status != "paid":
            await mark_payment_paid(session, payment)
            grant_prime(user, tariff=payment.tariff)
            await session.commit()
            try:
                await request.app.state.bot.send_message(user.telegram_id, ROBOKASSA_SUCCESS, reply_markup=prime_success())
            except Exception as exc:  # noqa: BLE001
                logger.info("could not notify paid user invoice=%s: %s", inv_id, exc.__class__.__name__)
        else:
            await session.rollback()
    return f"OK{inv_id}"


@router.get("/success", response_class=HTMLResponse)
async def robokassa_success() -> str:
    return """
    <html><body style='font-family:Inter,Arial,sans-serif;background:#0b0f1a;color:#f5f7ff;padding:32px'>
    <h1>✅ Оплата обрабатывается</h1>
    <p>Вернитесь в Telegram. PRIME PASS активируется после серверного подтверждения Robokassa.</p>
    </body></html>
    """


@router.get("/fail", response_class=HTMLResponse)
async def robokassa_fail() -> str:
    return """
    <html><body style='font-family:Inter,Arial,sans-serif;background:#0b0f1a;color:#f5f7ff;padding:32px'>
    <h1>⛔ Оплата не завершена</h1>
    <p>Вернитесь в Telegram и попробуйте ещё раз.</p>
    </body></html>
    """
