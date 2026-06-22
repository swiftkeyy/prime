"""
Unit-тесты для платёжной интеграции Platega.

Покрываемые задачи (spec: platega-payment, task 4):
  4.1  normalize_base_url
  4.2  validate_platega_settings
  4.3  is_confirmed_status / is_failed_status
  4.4  callback CONFIRMED — mark_payment_paid + grant_prime + "OK" 200
  4.5  callback невалидные заголовки — HTTP 403, grant_prime не вызван
  4.6  callback payment not found — HTTP 404
  4.7  callback несовпадение currency — HTTP 400
  4.8  callback несовпадение amount — HTTP 400
  4.9  повторный CONFIRMED (status == "paid") — "OK" 200, grant_prime не вызван повторно
  4.10 GET /platega/success — 200, HTML содержит "Telegram"
  4.11 GET /platega/fail — 200, HTML содержит "повтор"
  4.12 GET /platega/success — grant_prime НЕ вызывается
  4.13 исключение bot.send_message — логируется INFO, не пробрасывается
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from services.payments.platega import (
    PlategaError,
    is_confirmed_status,
    is_failed_status,
    normalize_base_url,
    validate_platega_settings,
)
from web.platega_routes import router as platega_router


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_app(settings, payment, mock_session, mock_bot) -> FastAPI:
    """Создаёт минимальное FastAPI-приложение с маршрутами Platega."""

    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator:
        yield mock_session

    app = FastAPI()
    app.state.settings = settings
    app.state.bot = mock_bot
    app.state.sessionmaker = _session_ctx

    app.include_router(platega_router)
    return app


def _make_mock_payment(status: str = "pending", invoice_id: str = "txn-abc-123") -> MagicMock:
    """Создаёт полностью мокированный объект Payment (без реального SQLAlchemy-объекта)."""
    user_mock = MagicMock()
    user_mock.telegram_id = 123456789

    # payment.awaitable_attrs.user must be awaitable and return user_mock
    # The route does: user = await payment.awaitable_attrs.user
    # So awaitable_attrs.user must itself be a coroutine / awaitable
    async def _user_coro():
        return user_mock

    attrs_mock = MagicMock()
    # Make .user a property that returns a coroutine each time it is accessed
    type(attrs_mock).user = property(lambda self: _user_coro())

    payment = MagicMock()
    payment.status = status
    payment.invoice_id = invoice_id
    payment.currency = "RUB"
    payment.amount = Decimal("299.00")
    payment.tariff = "7d"
    payment.user_id = 42
    payment.id = 1
    payment.awaitable_attrs = attrs_mock
    payment.user = user_mock
    return payment


def _make_mock_session() -> AsyncMock:
    """Возвращает мок AsyncSession с настроенными методами."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    return session


# ─────────────────────────────────────────────────────────────────────────────
# 4.1 normalize_base_url
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeBaseUrl:
    """Requirements: 4.3"""

    def test_no_trailing_slash(self):
        assert normalize_base_url("https://app.platega.io") == "https://app.platega.io"

    def test_single_trailing_slash(self):
        assert normalize_base_url("https://app.platega.io/") == "https://app.platega.io"

    def test_multiple_trailing_slashes(self):
        assert normalize_base_url("https://app.platega.io///") == "https://app.platega.io"

    def test_empty_string_returns_default(self):
        result = normalize_base_url("")
        assert result == "https://app.platega.io"
        assert not result.endswith("/")

    def test_whitespace_only_returns_default(self):
        result = normalize_base_url("   ")
        assert result == "https://app.platega.io"

    def test_url_with_path_no_slash(self):
        assert normalize_base_url("https://example.com/api") == "https://example.com/api"

    def test_url_with_path_and_slash(self):
        assert normalize_base_url("https://example.com/api/") == "https://example.com/api"


# ─────────────────────────────────────────────────────────────────────────────
# 4.2 validate_platega_settings
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatePlategaSettings:
    """Requirements: 4.1"""

    def test_empty_merchant_id_raises(self, mock_settings):
        mock_settings.PLATEGA_MERCHANT_ID = ""
        with pytest.raises(PlategaError):
            validate_platega_settings(mock_settings)

    def test_empty_secret_raises(self, mock_settings):
        mock_settings.PLATEGA_SECRET = ""
        with pytest.raises(PlategaError):
            validate_platega_settings(mock_settings)

    def test_whitespace_merchant_id_raises(self, mock_settings):
        mock_settings.PLATEGA_MERCHANT_ID = "   "
        with pytest.raises(PlategaError):
            validate_platega_settings(mock_settings)

    def test_whitespace_secret_raises(self, mock_settings):
        mock_settings.PLATEGA_SECRET = "  \t  "
        with pytest.raises(PlategaError):
            validate_platega_settings(mock_settings)

    def test_both_empty_raises(self, mock_settings):
        mock_settings.PLATEGA_MERCHANT_ID = ""
        mock_settings.PLATEGA_SECRET = ""
        with pytest.raises(PlategaError):
            validate_platega_settings(mock_settings)

    def test_valid_settings_does_not_raise(self, mock_settings):
        # Should not raise
        validate_platega_settings(mock_settings)

    def test_error_message_is_descriptive(self, mock_settings):
        mock_settings.PLATEGA_MERCHANT_ID = ""
        with pytest.raises(PlategaError, match=r"PLATEGA_MERCHANT_ID"):
            validate_platega_settings(mock_settings)


# ─────────────────────────────────────────────────────────────────────────────
# 4.3 is_confirmed_status / is_failed_status
# ─────────────────────────────────────────────────────────────────────────────

class TestStatusHelpers:
    """Requirements: 2.8, 2.11"""

    # is_confirmed_status
    def test_confirmed_true(self):
        assert is_confirmed_status("CONFIRMED") is True

    def test_confirmed_lowercase(self):
        assert is_confirmed_status("confirmed") is True

    def test_confirmed_mixed_case(self):
        assert is_confirmed_status("Confirmed") is True

    def test_confirmed_none_is_false(self):
        assert is_confirmed_status(None) is False

    def test_confirmed_empty_is_false(self):
        assert is_confirmed_status("") is False

    def test_confirmed_failed_is_false(self):
        assert is_confirmed_status("FAILED") is False

    def test_confirmed_canceled_is_false(self):
        assert is_confirmed_status("CANCELED") is False

    # is_failed_status
    def test_failed_canceled(self):
        assert is_failed_status("CANCELED") is True

    def test_failed_cancelled(self):
        assert is_failed_status("CANCELLED") is True

    def test_failed_failed(self):
        assert is_failed_status("FAILED") is True

    def test_failed_chargebacked(self):
        assert is_failed_status("CHARGEBACKED") is True

    def test_failed_lowercase(self):
        assert is_failed_status("failed") is True

    def test_failed_mixed_case(self):
        assert is_failed_status("Failed") is True

    def test_failed_none_is_false(self):
        assert is_failed_status(None) is False

    def test_failed_empty_is_false(self):
        assert is_failed_status("") is False

    def test_failed_confirmed_is_false(self):
        assert is_failed_status("CONFIRMED") is False


# ─────────────────────────────────────────────────────────────────────────────
# Общие фикстуры для тестов callback-хендлера
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_bot():
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def payment_pending():
    return _make_mock_payment(status="pending", invoice_id="txn-abc-123")


@pytest.fixture
def payment_paid():
    return _make_mock_payment(status="paid", invoice_id="txn-abc-123")


@pytest.fixture
def mock_session_pending():
    return _make_mock_session()


@pytest.fixture
def mock_session_paid():
    return _make_mock_session()


# ─────────────────────────────────────────────────────────────────────────────
# 4.4 Callback CONFIRMED → mark_payment_paid, grant_prime, "OK" 200
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_confirmed_success(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.8, 2.9"""
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment_pending)),
        patch("web.platega_routes.mark_payment_paid", new=AsyncMock()) as mock_mark,
        patch("web.platega_routes.grant_prime") as mock_grant,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED", "amount": "299.00", "currency": "RUB"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    assert response.status_code == 200
    assert response.text == "OK"
    mock_mark.assert_awaited_once()
    mock_grant.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 4.5 Callback невалидные заголовки → HTTP 403, grant_prime не вызван
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_invalid_headers_403(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.1, 2.2"""
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with patch("web.platega_routes.grant_prime") as mock_grant:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED"},
                headers={"X-MerchantId": "wrong-id", "X-Secret": "wrong-secret"},
            )

    assert response.status_code == 403
    mock_grant.assert_not_called()


@pytest.mark.asyncio
async def test_callback_missing_headers_403(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.1, 2.2 — заголовки отсутствуют"""
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with patch("web.platega_routes.grant_prime") as mock_grant:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED"},
            )

    assert response.status_code == 403
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4.6 Callback payment not found → HTTP 404
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_payment_not_found_404(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.4"""
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "nonexistent-txn", "status": "CONFIRMED"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 4.7 Callback несовпадение currency → HTTP 400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_currency_mismatch_400(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.5, 2.7"""
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)
    # payment.currency == "RUB", callback отправляет "USD"

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment_pending)),
        patch("web.platega_routes.grant_prime") as mock_grant,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED", "amount": "299.00", "currency": "USD"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    assert response.status_code == 400
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4.8 Callback несовпадение amount → HTTP 400
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_amount_mismatch_400(mock_settings, payment_pending, mock_session_pending, mock_bot):
    """Requirements: 2.6, 2.7"""
    # payment.amount == Decimal("299.00"), callback отправляет 100.00
    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment_pending)),
        patch("web.platega_routes.grant_prime") as mock_grant,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED", "amount": "100.00", "currency": "RUB"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    assert response.status_code == 400
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4.9 Повторный CONFIRMED при payment.status == "paid" → "OK" 200, grant_prime не вызван
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_callback_confirmed_idempotent(mock_settings, payment_paid, mock_session_paid, mock_bot):
    """Requirements: 2.10"""
    app = _make_app(mock_settings, payment_paid, mock_session_paid, mock_bot)

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment_paid)),
        patch("web.platega_routes.mark_payment_paid", new=AsyncMock()) as mock_mark,
        patch("web.platega_routes.grant_prime") as mock_grant,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED", "amount": "299.00", "currency": "RUB"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    assert response.status_code == 200
    assert response.text == "OK"
    mock_mark.assert_not_awaited()
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4.10 GET /platega/success → 200, HTML содержит "Telegram"
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_success_page_200_and_telegram_text(mock_settings, mock_bot):
    """Requirements: 3.1"""
    # Для success/fail не нужен sessionmaker с платежами
    app = _make_app(mock_settings, None, AsyncMock(), mock_bot)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/platega/success")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Telegram" in response.text


# ─────────────────────────────────────────────────────────────────────────────
# 4.11 GET /platega/fail → 200, HTML содержит текст про повторную попытку
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_page_200_and_retry_text(mock_settings, mock_bot):
    """Requirements: 3.2"""
    app = _make_app(mock_settings, None, AsyncMock(), mock_bot)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/platega/fail")

    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    # Страница должна содержать предложение повторить попытку
    assert "ещё раз" in response.text or "повтор" in response.text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4.12 GET /platega/success — grant_prime НЕ вызывается
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_success_page_does_not_call_grant_prime(mock_settings, mock_bot):
    """Requirements: 3.3"""
    app = _make_app(mock_settings, None, AsyncMock(), mock_bot)

    with patch("web.platega_routes.grant_prime") as mock_grant:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/platega/success")

    assert response.status_code == 200
    mock_grant.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4.13 Исключение bot.send_message → INFO лог, исключение не пробрасывается
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_notification_exception_logged_not_raised(mock_settings, payment_pending, mock_session_pending, caplog):
    """Requirements: 6.4"""
    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock(side_effect=Exception("Telegram API timeout"))

    app = _make_app(mock_settings, payment_pending, mock_session_pending, mock_bot)

    with (
        patch("web.platega_routes.get_payment_by_invoice", new=AsyncMock(return_value=payment_pending)),
        patch("web.platega_routes.mark_payment_paid", new=AsyncMock()),
        patch("web.platega_routes.grant_prime"),
        caplog.at_level(logging.INFO, logger="web.platega_routes"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/platega/callback",
                json={"id": "txn-abc-123", "status": "CONFIRMED", "amount": "299.00", "currency": "RUB"},
                headers={"X-MerchantId": "test-merchant-id", "X-Secret": "test-secret-key"},
            )

    # Основной поток не прервался — ответ "OK" 200
    assert response.status_code == 200
    assert response.text == "OK"

    # Исключение залогировано на уровне INFO
    info_records = [r for r in caplog.records if r.levelno == logging.INFO]
    assert info_records, "Expected at least one INFO log record for the notification exception"
    # Лог должен содержать имя класса исключения
    combined = " ".join(r.message for r in info_records)
    assert "Exception" in combined or "exception" in combined.lower() or "notify" in combined.lower() or "could not" in combined.lower()
