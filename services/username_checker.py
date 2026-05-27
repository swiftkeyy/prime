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
    """Base checker error."""


class UsernameCheckerNotConfigured(UsernameCheckError):
    """Fatal configuration error: MTProto credentials are missing/invalid."""


class UsernameCheckerRateLimited(UsernameCheckError):
    """Telegram temporarily rate-limited username checks."""

    def __init__(self, retry_after: int = 0) -> None:
        self.retry_after = max(0, int(retry_after or 0))
        super().__init__(f"Telegram username check is rate-limited for {self.retry_after} seconds")


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
        # account.checkUsername is strict but very sensitive. Keep a real pause,
        # otherwise Telegram gives huge flood waits and the bot becomes useless.
        self.delay_seconds = max(3.0, float(delay_seconds))
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = self.delay_seconds - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_event_loop().time()


KNOWN_BAD_USERNAMES = {
    "admin", "administrator", "support", "telegram", "settings", "username",
    "login", "help", "owner", "moderator", "security", "premium", "fragment",
    "wallet", "crypto", "stars", "store", "bot", "bots", "api", "web",
    "angel", "roman", "dobro", "zapor", "apple", "music", "money", "video",
    "cloud", "world", "super", "queen", "joker", "magic", "prime",
    "kvant", "novak", "sever", "orbit", "karat", "liver", "total", "lumen",
    "miron", "veter", "sonar", "nolan", "vital", "kredo", "nevan", "solen",
    "moral", "davor", "levin", "radon", "zoran", "valor", "raven", "rival",
    "venom", "vesta", "dorin", "buran", "lunar", "sokol", "volna", "iskra",
}


class MTProtoStrictUsernameChecker(RateLimiterMixin):
    """Strict Telegram checker that does not use resolveUsername live-scans.

    Why this version exists:
    - contacts.resolveUsername also gets huge FloodWait when spammed;
    - resolveUsername only answers whether username is assigned, not whether it
      is settable on account;
    - account.checkUsername is the only strict check, but it must be called very
      slowly and in small amounts.

    This checker therefore uses only account.checkUsername, throttles every call,
    and raises UsernameCheckerRateLimited immediately on FloodWait so handlers do
    not burn through 30 candidates and do not show fake "not found" messages.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        string_session: str,
        timeout: int = 7,
        delay_seconds: float = 3.0,
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
        self._strict_flood_until = 0.0
        self._strict_retry_after = 0

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
                request_retries=0,
                timeout=self.timeout,
                flood_sleep_threshold=0,
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
            logger.info("MTProto strict-only username checker connected own_username=%s", self._own_username or "none")

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
        if username in KNOWN_BAD_USERNAMES:
            logger.info("MTProto checkUsername @%s -> blocked by local known-bad list", username)
            return False

        await self._ensure_started()

        if self._own_username and username == self._own_username:
            logger.info("MTProto checkUsername @%s -> own username, skip", username)
            return False

        now = asyncio.get_event_loop().time()
        if now < self._strict_flood_until:
            retry_after = max(1, int(self._strict_flood_until - now))
            logger.warning("MTProto strict cooldown active, stop search; retry_after=%s sec", retry_after)
            raise UsernameCheckerRateLimited(retry_after)

        await self._rate_limit()

        try:
            from telethon.errors import FloodWaitError, RPCError
            from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameOccupiedError
            from telethon.tl.functions.account import CheckUsernameRequest
        except ImportError as exc:
            raise UsernameCheckerNotConfigured("telethon import error") from exc

        try:
            result = await asyncio.wait_for(
                self._client(CheckUsernameRequest(username), flood_sleep_threshold=0),  # type: ignore[misc]
                timeout=self.timeout,
            )
            allowed = bool(result)
            logger.info("MTProto account.checkUsername @%s -> %s", username, "settable" if allowed else "not settable")
            return allowed

        except (UsernameInvalidError, UsernameOccupiedError):
            logger.info("MTProto account.checkUsername @%s -> invalid/occupied", username)
            return False

        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0) or 0)
            # Keep local cooldown bounded for UX, but the Telegram account may be
            # locked longer. User should generate a fresh session or wait.
            cooldown = min(max(seconds, 60), 3600)
            self._strict_retry_after = seconds
            self._strict_flood_until = asyncio.get_event_loop().time() + cooldown
            logger.warning(
                "MTProto account.checkUsername flood wait @%s: %s sec; local cooldown=%s sec",
                username,
                seconds,
                cooldown,
            )
            raise UsernameCheckerRateLimited(seconds)

        except asyncio.TimeoutError:
            logger.warning("MTProto account.checkUsername timeout for @%s; candidate rejected", username)
            return False

        except RPCError as exc:
            msg = f"{exc.__class__.__name__} {str(exc)}".lower()
            blocked_markers = (
                "username_invalid", "username_occupied", "username_purchase_available",
                "purchase_available", "username_not_available", "not available",
                "occupied", "invalid", "premium", "collectible", "reserved", "auction",
            )
            if any(marker in msg for marker in blocked_markers):
                logger.info("MTProto account.checkUsername @%s -> blocked: %s", username, exc.__class__.__name__)
                return False
            logger.warning("MTProto account.checkUsername RPC error @%s: %s", username, msg[:180])
            return False

        except Exception as exc:
            logger.warning("MTProto account.checkUsername unexpected error @%s: %s: %s", username, exc.__class__.__name__, str(exc)[:180])
            return False


# Backwards-compatible names from earlier builds.
MTProtoResolveUsernameChecker = MTProtoStrictUsernameChecker
MTProtoSettableUsernameChecker = MTProtoStrictUsernameChecker


def _has_mtproto_credentials(settings: Settings) -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_STRING_SESSION)


def _build_mtproto_checker(settings: Settings) -> MTProtoStrictUsernameChecker:
    if not _has_mtproto_credentials(settings):
        raise UsernameCheckerNotConfigured(
            "MTProto credentials are missing. Set USERNAME_CHECK_MODE=mtproto, "
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION."
        )
    return MTProtoStrictUsernameChecker(
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
        logger.info("Using MTProto strict-only account.checkUsername checker")
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

    # v11 switches to strict-only account.checkUsername and drops resolve cache.
    cache_key = f"prime_nick:username:v11:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            if isinstance(cached, bytes):
                cached = cached.decode()
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        await redis.set(cache_key, "1" if available else "0", ex=positive_ttl if available else negative_ttl)
    return available
