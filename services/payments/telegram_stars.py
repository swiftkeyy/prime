from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings
from database.models import Payment, User
from database.queries import create_payment
from utils.formatters import tariff_title


async def create_stars_invoice(
    bot: Bot,
    session: AsyncSession,
    user: User,
    settings: Settings,
    tariff: str,
) -> Payment:
    amount = settings.stars_price(tariff)
    payment = await create_payment(
        session=session,
        user=user,
        amount=amount,
        currency="XTR",
        method="telegram_stars",
        tariff=tariff,
        status="pending",
    )
    payload = f"prime_nick:stars:{payment.invoice_id}:{tariff}"
    await bot.send_invoice(
        chat_id=user.telegram_id,
        title=f"PRIME PASS · {tariff_title(tariff)}",
        description="Расширенный доступ PRIME NICK для поиска редких Telegram username.",
        payload=payload,
        provider_token=settings.TELEGRAM_STARS_PROVIDER_TOKEN or None,
        currency="XTR",
        prices=[LabeledPrice(label="PRIME PASS", amount=amount)],
    )
    return payment


def parse_stars_payload(payload: str) -> tuple[str, str] | None:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "prime_nick" or parts[1] != "stars":
        return None
    return parts[2], parts[3]
