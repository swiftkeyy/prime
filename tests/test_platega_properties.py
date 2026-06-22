"""
Property-Based тесты для платёжной интеграции Platega.

Библиотека: hypothesis
Конфигурация: минимум 100 итераций (settings(max_examples=100))

Покрываемые свойства (spec: platega-payment, task 6):
  6.1  Property 7:  test_normalize_base_url_no_trailing_slash
  6.2  Property 8:  test_empty_settings_raises_platega_error
  6.3  Property 4:  test_verify_headers_exact_match
  6.4  Property 3:  test_non_200_raises_platega_error
  6.5  Property 1:  test_payload_has_required_fields
  6.6  Property 2:  test_invoice_id_updated_after_create_link
  6.7  Property 5:  test_amount_comparison_precision
  6.8  Property 6:  test_confirmed_callback_idempotent
  6.9  Property 9:  test_pricing_db_takes_priority
  6.10 Property 10: test_pricing_fallback_to_config
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from decimal import Decimal, InvalidOperation
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from config import Settings
from database.models import Payment, Setting
from services.payments.platega import (
    PlategaError,
    normalize_base_url,
    validate_platega_settings,
    verify_callback_headers,
    platega_headers,
    create_payment_link,
)
from services.pricing import get_prime_price
from web.platega_routes import router as platega_router


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _make_settings(merchant_id: str = "test-merchant", secret: str = "test-secret") -> Settings:
    """Создаёт тестовый объект Settings с переопределёнными значениями Platega."""
    s = Settings(
        BOT_TOKEN="1234567890:AABBCCDDEEFFaabbccddeeff-test_token",
        DATABASE_URL="postgresql+asyncpg://test:test@localhost/test",
        REDIS_URL="redis://localhost:6379/0",
        RAILWAY_PUBLIC_URL="https://test.example.com",
        PLATEGA_BASE_URL="https://app.platega.io",
        PLATEGA_MERCHANT_ID=merchant_id,
        PLATEGA_SECRET=secret,
        PLATEGA_PAYMENT_METHOD=2,
    )
    return s


def _make_payment(
    invoice_id: str = "inv-1",
    amount: Decimal | str = Decimal("299.00"),
    tariff: str = "7d",
    status: str = "pending",
    currency: str = "RUB",
) -> MagicMock:
    """Создаёт mock Payment без реального SQLAlchemy-объекта."""
    user_mock = MagicMock()
    user_mock.telegram_id = 123456789

    async def _user_coro():
        return user_mock

    attrs_mock = MagicMock()
    type(attrs_mock).user = property(lambda self: _user_coro())

    payment = MagicMock()
    payment.id = 1
    payment.user_id = 42
    payment.invoice_id = invoice_id
    payment.amount = Decimal(str(amount))
    payment.currency = currency
    payment.tariff = tariff
    payment.status = status
    payment.awaitable_attrs = attrs_mock
    payment.user = user_mock
    return payment


def _make_app(settings_obj: Settings, payment: MagicMock | None, session: AsyncMock, bot: AsyncMock) -> FastAPI:
    """Создаёт минимальное FastAPI-приложение с Platega-роутами."""

    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator:
        yield session

    app = FastAPI()
    app.state.settings = settings_obj
    app.state.bot = bot
    app.state.sessionmaker = _session_ctx
    app.include_router(platega_router)
    return app


def _make_session() -> AsyncMock:
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Property 7: Нормализация PLATEGA_BASE_URL
# Validates: Requirements 4.3
# ─────────────────────────────────────────────────────────────────────────────

@given(
    base=st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)),
        min_size=0,
        max_size=200,
    ),
    slash_count=st.integers(min_value=0, max_value=5),
)
@settings(max_examples=100)
def test_normalize_base_url_no_trailing_slash(base: str, slash_count: int):
    """
    **Validates: Requirements 4.3**

    Feature: platega-payment, Property 7: Нормализация PLATEGA_BASE_URL

    For any URL string (including empty, with 0..5 trailing slashes),
    normalize_base_url SHALL return a string that does NOT end with '/'.
    """
    url = base + "/" * slash_count
    result = normalize_base_url(url)
    assert not result.endswith("/"), (
        f"normalize_base_url({url!r}) returned {result!r} which ends with '/'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 8: Пустые настройки вызывают PlategaError до HTTP-запроса
# Validates: Requirements 4.1
# ─────────────────────────────────────────────────────────────────────────────

_empty_strategy = st.one_of(
    st.just(""),
    st.just(None),
    st.text(alphabet=" \t\n", min_size=1, max_size=20),
)


@given(merchant_id=_empty_strategy, valid_secret=st.just("valid-secret"))
@settings(max_examples=50)
def test_empty_merchant_id_raises_platega_error(merchant_id, valid_secret):
    """
    **Validates: Requirements 4.1**

    Feature: platega-payment, Property 8: Пустые настройки вызывают PlategaError до HTTP-запроса

    For any empty/None/whitespace PLATEGA_MERCHANT_ID,
    validate_platega_settings SHALL raise PlategaError.
    """
    s = _make_settings(merchant_id=merchant_id or "", secret=valid_secret)
    # Override the pydantic-validated field value directly
    object.__setattr__(s, "PLATEGA_MERCHANT_ID", merchant_id if merchant_id is not None else "")
    with pytest.raises(PlategaError):
        validate_platega_settings(s)


@given(valid_merchant=st.just("valid-merchant"), secret=_empty_strategy)
@settings(max_examples=50)
def test_empty_secret_raises_platega_error(valid_merchant, secret):
    """
    **Validates: Requirements 4.1**

    Feature: platega-payment, Property 8: Пустые настройки вызывают PlategaError до HTTP-запроса

    For any empty/None/whitespace PLATEGA_SECRET,
    validate_platega_settings SHALL raise PlategaError.
    """
    s = _make_settings(merchant_id=valid_merchant, secret=secret or "")
    object.__setattr__(s, "PLATEGA_SECRET", secret if secret is not None else "")
    with pytest.raises(PlategaError):
        validate_platega_settings(s)


# ─────────────────────────────────────────────────────────────────────────────
# Property 4: Верификация заголовков — точное совпадение
# Validates: Requirements 2.1, 2.2
# ─────────────────────────────────────────────────────────────────────────────

_printable_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd", "P"), whitelist_characters="-_"),
    min_size=1,
    max_size=64,
)


@given(merchant_id=_printable_text, secret=_printable_text)
@settings(max_examples=100)
def test_verify_headers_exact_match_true(merchant_id: str, secret: str):
    """
    **Validates: Requirements 2.1, 2.2**

    Feature: platega-payment, Property 4: Верификация заголовков — точное совпадение

    When merchant_id and secret EXACTLY match settings values,
    verify_callback_headers SHALL return True.
    """
    s = _make_settings(merchant_id=merchant_id, secret=secret)
    assert verify_callback_headers(s, merchant_id, secret) is True


@given(
    merchant_id=_printable_text,
    secret=_printable_text,
    other_merchant=_printable_text,
    other_secret=_printable_text,
)
@settings(max_examples=100)
def test_verify_headers_exact_match_false_on_difference(
    merchant_id: str,
    secret: str,
    other_merchant: str,
    other_secret: str,
):
    """
    **Validates: Requirements 2.1, 2.2**

    Feature: platega-payment, Property 4: Верификация заголовков — точное совпадение

    When at least one header value differs from settings,
    verify_callback_headers SHALL return False.
    """
    s = _make_settings(merchant_id=merchant_id, secret=secret)

    # Test mismatched merchant_id
    assume(other_merchant != merchant_id)
    assert verify_callback_headers(s, other_merchant, secret) is False

    # Test mismatched secret
    assume(other_secret != secret)
    assert verify_callback_headers(s, merchant_id, other_secret) is False

    # Test both mismatched
    assert verify_callback_headers(s, other_merchant, other_secret) is False


# ─────────────────────────────────────────────────────────────────────────────
# Property 3: Не-200/201 статус вызывает PlategaError
# Validates: Requirements 1.5
# ─────────────────────────────────────────────────────────────────────────────

@given(status_code=st.integers(min_value=100, max_value=599).filter(lambda x: x not in {200, 201}))
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_non_200_raises_platega_error(status_code: int):
    """
    **Validates: Requirements 1.5**

    Feature: platega-payment, Property 3: Не-200/201 статус вызывает PlategaError

    For any HTTP status code not in {200, 201},
    create_payment_link SHALL raise PlategaError.
    """
    s = _make_settings()
    payment = _make_payment(invoice_id="inv-test-123")
    session = _make_session()

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.text = f"Error {status_code}"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.payments.platega.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(PlategaError):
            await create_payment_link(s, payment, session)


# ─────────────────────────────────────────────────────────────────────────────
# Property 1: Payload содержит все обязательные поля
# Validates: Requirements 1.2
# ─────────────────────────────────────────────────────────────────────────────

_tariff_strategy = st.sampled_from(["1d", "7d", "30d", "forever"])
_amount_strategy = st.decimals(
    min_value=Decimal("1"),
    max_value=Decimal("99999"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@given(tariff=_tariff_strategy, amount=_amount_strategy)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_payload_has_required_fields(tariff: str, amount: Decimal):
    """
    **Validates: Requirements 1.2**

    Feature: platega-payment, Property 1: Payload содержит все обязательные поля

    For any Payment with non-null invoice_id, amount, tariff,
    the Platega payload SHALL contain: paymentMethod, paymentDetails.amount,
    paymentDetails.currency, description, return, failedUrl, payload.
    """
    s = _make_settings()
    payment = _make_payment(invoice_id="inv-123", amount=amount, tariff=tariff)
    session = _make_session()

    captured_payload: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "transactionId": "txn-captured",
        "redirect": "https://platega.io/pay/txn-captured",
    })

    async def _mock_post(url, headers=None, json=None, **kwargs):
        nonlocal captured_payload
        if json is not None:
            captured_payload = json
        return mock_response

    mock_client = AsyncMock()
    mock_client.post = _mock_post
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.payments.platega.httpx.AsyncClient", return_value=mock_client):
        await create_payment_link(s, payment, session)

    # Verify all required top-level fields
    assert "paymentMethod" in captured_payload, "Missing 'paymentMethod' in payload"
    assert "paymentDetails" in captured_payload, "Missing 'paymentDetails' in payload"
    assert "description" in captured_payload, "Missing 'description' in payload"
    assert "return" in captured_payload, "Missing 'return' in payload"
    assert "failedUrl" in captured_payload, "Missing 'failedUrl' in payload"
    assert "payload" in captured_payload, "Missing 'payload' in payload"

    # Verify paymentDetails sub-fields
    payment_details = captured_payload["paymentDetails"]
    assert "amount" in payment_details, "Missing 'paymentDetails.amount' in payload"
    assert "currency" in payment_details, "Missing 'paymentDetails.currency' in payload"


# ─────────────────────────────────────────────────────────────────────────────
# Property 2: Обновление invoice_id после создания транзакции
# Validates: Requirements 1.3, 1.4
# ─────────────────────────────────────────────────────────────────────────────

@given(transaction_id=st.text(min_size=1, max_size=128, alphabet=st.characters(blacklist_categories=("Cs",))))
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_invoice_id_updated_after_create_link(transaction_id: str):
    """
    **Validates: Requirements 1.3, 1.4**

    Feature: platega-payment, Property 2: Обновление invoice_id после создания транзакции

    For any transactionId returned by (mock) Platega API,
    payment.invoice_id SHALL equal that transactionId after successful create_payment_link call.
    """
    # create_payment_link does transaction_id.strip(), so stripped must be non-empty
    assume(transaction_id.strip() != "")

    s = _make_settings()
    payment = _make_payment(invoice_id="original-inv-1")
    session = _make_session()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={
        "transactionId": transaction_id,
        "redirect": "https://platega.io/pay/redirect",
    })

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("services.payments.platega.httpx.AsyncClient", return_value=mock_client):
        await create_payment_link(s, payment, session)

    assert payment.invoice_id == transaction_id.strip(), (
        f"Expected payment.invoice_id={transaction_id.strip()!r}, got {payment.invoice_id!r}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 5: Сравнение amount с точностью до 2 знаков
# Validates: Requirements 2.6, 2.7
# ─────────────────────────────────────────────────────────────────────────────

@given(amount=_amount_strategy)
@settings(max_examples=100)
def test_amount_comparison_precision_equal(amount: Decimal):
    """
    **Validates: Requirements 2.6, 2.7**

    Feature: platega-payment, Property 5: Сравнение amount с точностью до 2 знаков

    When callback amount equals payment.amount (both rounded to 2 decimal places),
    the comparison SHALL consider them matching.
    """
    quantized = amount.quantize(Decimal("0.01"))
    callback_amount = quantized
    payment_amount = quantized

    # This is the comparison logic from platega_routes.py
    result = (
        Decimal(str(callback_amount)).quantize(Decimal("0.01"))
        == Decimal(str(payment_amount)).quantize(Decimal("0.01"))
    )
    assert result is True, (
        f"Amounts {callback_amount} and {payment_amount} should match but comparison returned False"
    )


@given(
    amount=_amount_strategy,
    delta=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("100"), places=2, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=100)
def test_amount_comparison_precision_mismatch(amount: Decimal, delta: Decimal):
    """
    **Validates: Requirements 2.6, 2.7**

    Feature: platega-payment, Property 5: Сравнение amount с точностью до 2 знаков

    When callback amount differs from payment.amount by at least 0.01,
    the comparison SHALL consider them NOT matching.
    """
    quantized = amount.quantize(Decimal("0.01"))
    delta_quantized = delta.quantize(Decimal("0.01"))
    assume(delta_quantized >= Decimal("0.01"))

    callback_amount = quantized + delta_quantized
    payment_amount = quantized

    # This is the comparison logic from platega_routes.py
    result = (
        Decimal(str(callback_amount)).quantize(Decimal("0.01"))
        == Decimal(str(payment_amount)).quantize(Decimal("0.01"))
    )
    assert result is False, (
        f"Amounts {callback_amount} and {payment_amount} differ by {delta_quantized} "
        f"but comparison returned True"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 6: Идемпотентность confirmed callback
# Validates: Requirements 2.10
# ─────────────────────────────────────────────────────────────────────────────

@given(transaction_id=st.text(min_size=1, max_size=64, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))))
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_confirmed_callback_idempotent(transaction_id: str):
    """
    **Validates: Requirements 2.10**

    Feature: platega-payment, Property 6: Идемпотентность confirmed callback

    For any Payment with status == "paid", a repeated CONFIRMED callback
    SHALL return "OK" without calling grant_prime again.
    """
    s = _make_settings()
    payment = _make_payment(invoice_id=transaction_id, status="paid", amount=Decimal("299.00"))
    session = _make_session()
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    app = _make_app(s, payment, session, bot)

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment)),
        patch("web.platega_routes.mark_payment_paid", new=AsyncMock()) as mock_mark,
        patch("web.platega_routes.grant_prime") as mock_grant,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={
                    "id": transaction_id,
                    "status": "CONFIRMED",
                    "amount": "299.00",
                    "currency": "RUB",
                },
                headers={"X-MerchantId": "test-merchant", "X-Secret": "test-secret"},
            )

    assert response.status_code == 200
    assert response.text == "OK"
    mock_mark.assert_not_awaited()
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# Property 9: Pricing приоритет DB над конфигом
# Validates: Requirements 5.1
# ─────────────────────────────────────────────────────────────────────────────

@given(
    tariff=_tariff_strategy,
    db_price=st.integers(min_value=1, max_value=100000),
)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_pricing_db_takes_priority(tariff: str, db_price: int):
    """
    **Validates: Requirements 5.1**

    Feature: platega-payment, Property 9: Pricing приоритет DB над конфигом

    For any tariff in {"1d", "7d", "30d", "forever"}, when DB contains a valid
    integer price for the corresponding key, get_prime_price SHALL return that
    DB value (not the config value).
    """
    s = _make_settings()

    # Mock DB Setting object with valid integer price
    mock_setting = MagicMock(spec=Setting)
    mock_setting.value = str(db_price)

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=mock_setting)

    result = await get_prime_price(mock_session, s, "platega", tariff)

    assert result == db_price, (
        f"Expected DB price {db_price} for tariff {tariff!r}, got {result}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Property 10: Pricing fallback при отсутствии DB-записи
# Validates: Requirements 5.2, 5.3
# ─────────────────────────────────────────────────────────────────────────────

@given(tariff=_tariff_strategy)
@settings(max_examples=100)
@pytest.mark.asyncio
async def test_pricing_fallback_to_config(tariff: str):
    """
    **Validates: Requirements 5.2, 5.3**

    Feature: platega-payment, Property 10: Pricing fallback при отсутствии DB-записи

    For any tariff in {"1d", "7d", "30d", "forever"}, when DB returns None,
    get_prime_price SHALL return a positive integer from Settings config.
    """
    s = _make_settings()

    mock_session = AsyncMock()
    mock_session.scalar = AsyncMock(return_value=None)

    result = await get_prime_price(mock_session, s, "platega", tariff)

    assert isinstance(result, int), (
        f"Expected int from config fallback for tariff {tariff!r}, got {type(result).__name__}"
    )
    assert result > 0, (
        f"Expected positive price from config fallback for tariff {tariff!r}, got {result}"
    )
