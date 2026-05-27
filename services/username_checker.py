from __future__ import annotations

import asyncio
import logging
import random
from typing import Protocol

from redis.asyncio import Redis

from config import Settings
from utils.validators import is_valid_username

logger = logging.getLogger(__name__)


class UsernameCheckError(RuntimeError):
    """Temporary checker error. Search code may skip candidate or show unavailable."""


class UsernameCheckerNotConfigured(UsernameCheckError):
    """Fatal configuration error: MTProto credentials are missing/invalid."""


class UsernameCheckerAdapter(Protocol):
    async def is_available(self, username: str) -> bool: ...


class MockUsernameChecker:
    async def start(self) -> None:
        logger.warning("USERNAME_CHECK_MODE=mock is enabled. Use only for local tests.")

    async def is_available(self, username: str) -> bool:
        await asyncio.sleep(0.05)
        return random.random() < 0.18


class FailClosedUsernameChecker:
    """Never returns false positives when production checker is not configured."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def start(self) -> None:
        logger.error("Username checker is disabled: %s", self.reason)

    async def is_available(self, username: str) -> bool:
        logger.error("Username check refused for @%s: %s", username, self.reason)
        raise UsernameCheckerNotConfigured(self.reason)


class RateLimiterMixin:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = max(0.05, float(delay_seconds))
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = self.delay_seconds - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_event_loop().time()


class MTProtoSettableUsernameChecker(RateLimiterMixin):
    """Strict Telegram checker for usernames a real account can set.

    IMPORTANT: Fragment/t.me/Bot API can say that a nickname looks free while
    Telegram will still reject it in profile settings. PRIME NICK must use
    account.checkUsername through a real user MTProto session. The nickname is
    shown only when Telegram itself returns True for the current account.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        string_session: str,
        timeout: int = 7,
        delay_seconds: float = 0.35,
    ) -> None:
        super().__init__(delay_seconds=delay_seconds)
        self.api_id = int(api_id)
        self.api_hash = api_hash.strip()
        self.string_session = string_session.strip()
        self.timeout = int(timeout)
        self._client = None
        self._started = False
        self._start_lock = asyncio.Lock()
        self._own_username: str | None = None

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return

            if not self.api_id or not self.api_hash or not self.string_session:
                raise UsernameCheckerNotConfigured(
                    "MTProto credentials are missing. Set TELEGRAM_API_ID, "
                    "TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION in Railway Variables."
                )

            try:
                from telethon import TelegramClient
                from telethon.sessions import StringSession
            except ImportError as exc:
                raise UsernameCheckerNotConfigured("telethon is not installed. Add telethon to requirements.txt") from exc

            self._client = TelegramClient(
                StringSession(self.string_session),
                self.api_id,
                self.api_hash,
                sequential_updates=True,
                connection_retries=2,
                request_retries=1,
                timeout=self.timeout,
            )
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise UsernameCheckerNotConfigured(
                    "TELEGRAM_STRING_SESSION is invalid or expired. "
                    "Regenerate it with scripts/create_telethon_session.py"
                )
            me = await self._client.get_me()
            self._own_username = (getattr(me, "username", None) or "").lower() or None
            self._started = True
            logger.info("MTProto settable username checker connected own_username=%s", self._own_username or "none")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
        self._started = False
        logger.info("MTProto username checker disconnected")

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    async def is_available(self, username: str) -> bool:
        username = username.lower().lstrip("@")
        if not is_valid_username(username):
            return False

        await self._ensure_started()
        await self._rate_limit()

        try:
            from telethon.errors import FloodWaitError, RPCError
            from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameOccupiedError
            from telethon.tl.functions.account import CheckUsernameRequest
        except ImportError as exc:
            raise UsernameCheckerNotConfigured("telethon import error") from exc

        if self._own_username and username == self._own_username:
            logger.info("MTProto check @%s -> own username, skip", username)
            return False

        try:
            result = await asyncio.wait_for(
                self._client(CheckUsernameRequest(username)),  # type: ignore[misc]
                timeout=self.timeout,
            )
            logger.info("MTProto account.checkUsername @%s -> %s", username, bool(result))
            return bool(result)

        except (UsernameOccupiedError, UsernameInvalidError):
            logger.info("MTProto account.checkUsername @%s -> occupied/invalid", username)
            return False

        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0) or 0)
            logger.warning("MTProto flood wait while checking @%s: %s sec", username, seconds)
            raise UsernameCheckError(f"mtproto flood_wait {seconds}s") from exc

        except asyncio.TimeoutError:
            logger.warning("MTProto timeout for @%s; candidate skipped", username)
            return False

        except RPCError as exc:
            # Telegram has several non-settable states: collectible/auction/reserved/
            # premium/unavailable. They are not free, but not fatal for the whole search.
            message = f"{exc.__class__.__name__} {str(exc)}".lower()
            blocked_markers = (
                "username_occupied",
                "username_invalid",
                "username_purchase_available",
                "purchase_available",
                "username_not_available",
                "not available",
                "occupied",
                "invalid",
                "premium",
                "collectible",
                "reserved",
                "auction",
            )
            if any(marker in message for marker in blocked_markers):
                logger.info("MTProto account.checkUsername @%s -> not settable: %s", username, exc.__class__.__name__)
                return False
            logger.warning("MTProto RPC error for @%s: %s", username, message[:180])
            return False

        except Exception as exc:
            # Do not show a fake 'available' result on unknown errors. Skip candidate.
            logger.warning("MTProto unexpected error for @%s: %s", username, exc.__class__.__name__)
            return False


def _has_mtproto_credentials(settings: Settings) -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_STRING_SESSION)


def _build_mtproto_checker(settings: Settings) -> MTProtoSettableUsernameChecker:
    if not _has_mtproto_credentials(settings):
        raise UsernameCheckerNotConfigured(
            "MTProto credentials are missing. Set USERNAME_CHECK_MODE=mtproto, "
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION."
        )
    return MTProtoSettableUsernameChecker(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        string_session=settings.TELEGRAM_STRING_SESSION,
        timeout=settings.USERNAME_CHECK_TIMEOUT,
        delay_seconds=settings.MTPROTO_CHECK_DELAY_SECONDS,
    )


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    mode = settings.USERNAME_CHECK_MODE
    logger.info("PRIME NICK username checker mode from env: %s", mode)

    if mode == "mock":
        return MockUsernameChecker()

    if _has_mtproto_credentials(settings):
        logger.info("Using strict MTProto account.checkUsername checker")
        return _build_mtproto_checker(settings)

    reason = (
        "Strict username checking is not configured. Set TELEGRAM_API_ID, "
        "TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION in Railway Variables. "
        "Fragment/t.me/BotAPI checking is disabled because it returns false positives."
    )
    return FailClosedUsernameChecker(reason)


async def is_username_available(
    username: str,
    *,
    checker: UsernameCheckerAdapter,
    redis: Redis | None = None,
    positive_ttl: int = 20,
    negative_ttl: int = 300,
) -> bool:
    username = username.lower().lstrip("@")
    if not is_valid_username(username):
        return False

    # v6 drops old false-positive cache records from Fragment/BotAPI builds.
    cache_key = f"prime_nick:username:v6:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        # Free usernames can be taken any second; keep positive cache very short.
        await redis.set(cache_key, "1" if available else "0", ex=positive_ttl if available else negative_ttl)
    return available
