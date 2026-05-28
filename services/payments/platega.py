from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Payment, User
from database.queries import create_payment
from services.pricing import get_prime_price
from utils.formatters import tariff_title

logger = logging.getLogger(__name__)


class PlategaError(RuntimeError):
    pass


def normalize_base_url(url: str) -> str:
    return (url or "https://app.platega.io").rstrip("/")


def platega_headers(settings: Settings) -> dict[str, str]:
    return {
        "X-MerchantId": settings.PLATEGA_MERCHANT_ID,
        "X-Secret": settings.PLATEGA_SECRET,
        "Content-Type": "application/json",
    }


def validate_platega_settings(settings: Settings) -> None:
    if not settings.PLATEGA_MERCHANT_ID or not settings.PLATEGA_SECRET:
        raise PlategaError("PLATEGA_MERCHANT_ID / PLATEGA_SECRET are not configured")


async def create_platega_payment(session: AsyncSession, user: User, settings: Settings, tariff: str) -> Payment:
    amount = await get_prime_price(session, settings, "platega", tariff)
    return await create_payment(
        session=session,
        user=user,
        amount=amount,
        currency="RUB",
        method="platega",
        tariff=tariff,
        status="pending",
    )


def build_return_url(settings: Settings) -> str:
    return f"{settings.RAILWAY_PUBLIC_URL}/platega/success"


def build_fail_url(settings: Settings) -> str:
    return f"{settings.RAILWAY_PUBLIC_URL}/platega/fail"


async def create_payment_link(settings: Settings, payment: Payment) -> str:
    """Create Platega transaction and return redirect URL.

    Platega creates transaction IDs itself, so we first create a local Payment,
    then replace payment.invoice_id with Platega transactionId. PRIME is issued
    only from /platega/callback after CONFIRMED status and amount validation.
    """
    validate_platega_settings(settings)
    if not payment.invoice_id:
        raise PlategaError("payment.invoice_id is required")

    base_url = normalize_base_url(settings.PLATEGA_BASE_URL)
    payload = {
        "paymentMethod": settings.PLATEGA_PAYMENT_METHOD,
        "paymentDetails": {
            "amount": int(Decimal(str(payment.amount))),
            "currency": "RUB",
        },
        "description": f"PRIME PASS · {tariff_title(payment.tariff)} · invoice {payment.invoice_id}",
        "return": build_return_url(settings),
        "failedUrl": build_fail_url(settings),
        "payload": json.dumps(
            {
                "payment_id": payment.id,
                "invoice_id": payment.invoice_id,
                "user_id": payment.user_id,
                "tariff": payment.tariff,
            },
            ensure_ascii=False,
        ),
    }

    timeout = httpx.Timeout(connect=8.0, read=20.0, write=8.0, pool=8.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        try:
            response = await client.post("/transaction/process", headers=platega_headers(settings), json=payload)
        except httpx.HTTPError as exc:
            logger.warning("platega create transaction network error: %s", exc.__class__.__name__)
            raise PlategaError("Platega network error") from exc

    if response.status_code not in {200, 201}:
        logger.warning("platega create transaction failed status=%s body=%s", response.status_code, response.text[:500])
        raise PlategaError("Platega rejected transaction")

    data: dict[str, Any] = response.json()
    transaction_id = str(data.get("transactionId") or data.get("id") or "").strip()
    redirect_url = str(data.get("redirect") or "").strip()
    if not transaction_id or not redirect_url:
        logger.warning("platega invalid transaction response: %s", data)
        raise PlategaError("Invalid Platega response")

    payment.invoice_id = transaction_id
    payment.status = str(data.get("status") or "pending").lower()
    if payment.status not in {"created", "pending"}:
        payment.status = "pending"
    await session.flush()
    return redirect_url


async def get_transaction_status(settings: Settings, transaction_id: str) -> dict[str, Any]:
    validate_platega_settings(settings)
    base_url = normalize_base_url(settings.PLATEGA_BASE_URL)
    timeout = httpx.Timeout(connect=8.0, read=15.0, write=8.0, pool=8.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        response = await client.get(f"/transaction/{transaction_id}", headers=platega_headers(settings))
    if response.status_code != 200:
        raise PlategaError(f"status check failed: {response.status_code}")
    return response.json()


def verify_callback_headers(settings: Settings, merchant_id: str | None, secret: str | None) -> bool:
    return (merchant_id or "") == settings.PLATEGA_MERCHANT_ID and (secret or "") == settings.PLATEGA_SECRET


def is_confirmed_status(status: str | None) -> bool:
    return (status or "").upper() == "CONFIRMED"


def is_failed_status(status: str | None) -> bool:
    return (status or "").upper() in {"CANCELED", "CANCELLED", "FAILED", "CHARGEBACKED"}
