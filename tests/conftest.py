"""
Pytest fixtures for platega-payment tests.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

import pytest

from config import Settings
from database.models import Payment


@pytest.fixture
def mock_settings() -> Settings:
    """Settings с тестовыми значениями Platega и минимальными обязательными полями."""
    return Settings(
        BOT_TOKEN="1234567890:AABBCCDDEEFFaabbccddeeff-test_token",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        REDIS_URL="redis://localhost:6379/0",
        RAILWAY_PUBLIC_URL="https://test.example.com",
        PLATEGA_BASE_URL="https://app.platega.io",
        PLATEGA_MERCHANT_ID="test-merchant-id",
        PLATEGA_SECRET="test-secret-key",
        PLATEGA_PAYMENT_METHOD=2,
    )


@pytest.fixture
def make_payment() -> Callable[..., Payment]:
    """Фабрика объектов Payment с разумными значениями по умолчанию."""

    def _factory(
        id: int = 1,
        user_id: int = 42,
        amount: Decimal | int | str = Decimal("299.00"),
        currency: str = "RUB",
        method: str = "platega",
        status: str = "pending",
        invoice_id: str | None = "1",
        tariff: str = "7d",
    ) -> Payment:
        payment = Payment(
            id=id,
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency=currency,
            method=method,
            status=status,
            invoice_id=invoice_id,
            tariff=tariff,
        )
        return payment

    return _factory
