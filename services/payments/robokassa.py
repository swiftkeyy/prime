from __future__ import annotations

import hashlib
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Payment, User
from database.queries import create_payment
from utils.formatters import tariff_title

ROBOKASSA_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"


def format_out_sum(amount: Decimal | int | str) -> str:
    value = Decimal(str(amount))
    if value == value.to_integral():
        return str(int(value))
    return f"{value:.2f}"


def md5_upper(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest().upper()


def payment_signature(settings: Settings, out_sum: str, inv_id: str) -> str:
    return md5_upper(f"{settings.ROBOKASSA_LOGIN}:{out_sum}:{inv_id}:{settings.ROBOKASSA_PASSWORD_1}")


def result_signature(settings: Settings, out_sum: str, inv_id: str) -> str:
    return md5_upper(f"{out_sum}:{inv_id}:{settings.ROBOKASSA_PASSWORD_2}")


def verify_result_signature(settings: Settings, out_sum: str, inv_id: str, signature: str) -> bool:
    expected = result_signature(settings, out_sum, inv_id)
    return expected.upper() == (signature or "").upper()


async def create_robokassa_payment(session: AsyncSession, user: User, settings: Settings, tariff: str) -> Payment:
    amount = settings.rub_price(tariff)
    return await create_payment(
        session=session,
        user=user,
        amount=amount,
        currency="RUB",
        method="robokassa",
        tariff=tariff,
        status="pending",
    )


def build_payment_url(settings: Settings, payment: Payment) -> str:
    if not payment.invoice_id:
        raise ValueError("payment.invoice_id is required")
    out_sum = format_out_sum(payment.amount)
    inv_id = payment.invoice_id
    params = {
        "MerchantLogin": settings.ROBOKASSA_LOGIN,
        "OutSum": out_sum,
        "InvId": inv_id,
        "Description": f"PRIME PASS · {tariff_title(payment.tariff)}",
        "SignatureValue": payment_signature(settings, out_sum, inv_id),
        "Culture": "ru",
        "Encoding": "utf-8",
    }
    if settings.ROBOKASSA_TEST_MODE:
        params["IsTest"] = "1"
    return f"{ROBOKASSA_URL}?{urlencode(params)}"
