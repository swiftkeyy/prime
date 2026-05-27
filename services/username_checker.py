from __future__ import annotations

import asyncio
import logging
import random
import re
from typing import Protocol

import httpx
from redis.asyncio import Redis

from config import Settings
from utils.validators import is_valid_username

logger = logging.getLogger(__name__)


class UsernameCheckError(RuntimeError):
    pass


class UsernameCheckerAdapter(Protocol):
    async def is_available(self, username: str) -> bool: ...


class MockUsernameChecker:
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
        raise UsernameCheckError(self.reason)


class RateLimiterMixin:
    def __init__(self, delay_seconds: float) -> None:
        self.delay_seconds = delay_seconds
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

    contacts.resolveUsername only answers whether a username resolves to an
    entity. It can miss usernames that are technically not occupied but still
    cannot be set by a normal Telegram account. account.checkUsername is stricter:
    it returns True only when Telegram says the current account can set this
    username right now. That is what PRIME NICK needs before showing a result.
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
        self.api_id = api_id
        self.api_hash = api_hash
        self.string_session = string_session
        self.timeout = timeout
        self._client = None
        self._started = False
        self._start_lock = asyncio.Lock()
        self._own_username: str | None = None

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return

            try:
                from telethon import TelegramClient
                from telethon.sessions import StringSession
            except ImportError as exc:
                raise RuntimeError("telethon is not installed. Add telethon to requirements.txt") from exc

            self._client = TelegramClient(
                StringSession(self.string_session),
                self.api_id,
                self.api_hash,
                sequential_updates=True,
            )
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise RuntimeError(
                    "TELEGRAM_STRING_SESSION is invalid or not authorized. "
                    "Generate it with scripts/create_telethon_session.py"
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
        await self._ensure_started()
        await self._rate_limit()

        try:
            from telethon.errors import FloodWaitError, RPCError
            from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameOccupiedError
            from telethon.tl.functions.account import CheckUsernameRequest
        except ImportError as exc:
            raise UsernameCheckError("telethon import error") from exc

        if self._own_username and username.lower() == self._own_username:
            logger.info("MTProto account.checkUsername @%s -> own username, skip", username)
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
            logger.warning("MTProto username checker flood wait: %s seconds", seconds)
            raise UsernameCheckError(f"mtproto flood wait {seconds}s") from exc
        except asyncio.TimeoutError as exc:
            logger.warning("MTProto username checker timeout for @%s", username)
            raise UsernameCheckError("mtproto timeout") from exc
        except RPCError as exc:
            message = str(exc).lower()
            blocked_markers = (
                "username_occupied",
                "username_invalid",
                "username_purchase_available",
                "purchase_available",
                "username_not_available",
                "not available",
                "occupied",
                "invalid",
            )
            if any(marker in message for marker in blocked_markers):
                logger.info("MTProto account.checkUsername @%s -> blocked: %s", username, exc.__class__.__name__)
                return False
            logger.warning("MTProto RPC error for @%s: %s %s", username, exc.__class__.__name__, str(exc)[:160])
            raise UsernameCheckError("mtproto rpc error") from exc
        except Exception as exc:
            logger.warning("MTProto unexpected error for @%s: %s", username, exc.__class__.__name__)
            raise UsernameCheckError("mtproto unexpected error") from exc


class TelegramBotApiUsernameChecker(RateLimiterMixin):
    """Legacy checker. Not safe for personal usernames; kept for mock/dev only."""

    API_URL = "https://api.telegram.org/bot{token}/getChat"

    def __init__(self, bot_token: str, timeout: int = 7, delay_seconds: float = 0.35) -> None:
        super().__init__(delay_seconds=delay_seconds)
        self.bot_token = bot_token
        self.timeout = timeout

    async def is_available(self, username: str) -> bool:
        await self._rate_limit()
        url = self.API_URL.format(token=self.bot_token)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, params={"chat_id": f"@{username}"})
        except httpx.HTTPError as exc:
            logger.warning("telegram bot api checker network error: %s", exc.__class__.__name__)
            raise UsernameCheckError("telegram bot api network error") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"telegram bot api temporary status {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise UsernameCheckError("telegram bot api invalid json") from exc

        if payload.get("ok") is True:
            return False

        description = str(payload.get("description", "")).lower()
        error_code = int(payload.get("error_code") or response.status_code or 0)

        if error_code == 400 and "chat not found" in description:
            return True

        raise UsernameCheckError("telegram bot api unexpected response")


class TMeHttpUsernameChecker(RateLimiterMixin):
    def __init__(self, timeout: int = 7) -> None:
        super().__init__(delay_seconds=0.35)
        self.timeout = timeout

    async def is_available(self, username: str) -> bool:
        await self._rate_limit()
        url = f"https://t.me/{username}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
                response = await client.get(url, headers={"User-Agent": "PRIME-NICK/1.0"})
        except httpx.HTTPError as exc:
            raise UsernameCheckError("t.me network error") from exc

        if response.status_code == 404:
            return True
        if response.status_code in {200, 301, 302, 303, 307, 308}:
            return False
        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"t.me temporary status {response.status_code}")
        return False


class FragmentUsernameChecker(RateLimiterMixin):
    """Fragment-only guard. Not enough for production by itself."""

    BASE_URL = "https://fragment.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36 PRIME-NICK/1.0"
    )

    BLOCKED_CLASSES = (
        "tm-status-taken",
        "tm-status-avail",
        "tm-status-unavail",
        "tm-status-sold",
        "tm-status-resale",
    )
    BLOCKED_PHRASES = (
        "already taken",
        "is taken",
        "unavailable",
        "not available",
        "sale price",
        "place bid",
        "bid history",
        "minimum bid",
        "auction",
        "for sale",
        "sold",
        "owner",
        "assigned to",
        "collectible username",
        "anonymous number",
    )

    def __init__(self, timeout: int = 7, delay_seconds: float = 0.8) -> None:
        super().__init__(delay_seconds=delay_seconds)
        self.timeout = timeout

    def _headers(self, username: str) -> dict[str, str]:
        return {
            "User-Agent": self.USER_AGENT,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ru;q=0.8",
            "X-Requested-With": "XMLHttpRequest",
            "X-Aj-Referer": f"{self.BASE_URL}/?query={username}",
            "Referer": f"{self.BASE_URL}/?query={username}",
            "Connection": "keep-alive",
        }

    @classmethod
    def _is_blocked_by_fragment(cls, markup: str) -> bool:
        text = re.sub(r"\s+", " ", markup.lower())
        if any(item in text for item in cls.BLOCKED_CLASSES):
            return True
        return any(item in text for item in cls.BLOCKED_PHRASES)

    async def is_available(self, username: str) -> bool:
        await self._rate_limit()
        url = f"{self.BASE_URL}/username/{username}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=self._headers(username))
        except httpx.HTTPError as exc:
            raise UsernameCheckError("fragment network error") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"fragment temporary status {response.status_code}")
        if response.status_code != 200:
            raise UsernameCheckError(f"fragment unexpected status {response.status_code}")

        try:
            payload = response.json()
        except ValueError:
            markup = response.text
        else:
            markup = str(payload.get("h") or payload.get("html") or payload)

        return not self._is_blocked_by_fragment(markup)


class FragmentThenMTProtoChecker:
    """Optional belt-and-braces mode. MTProto is still the final authority."""

    def __init__(self, fragment_checker: FragmentUsernameChecker, mtproto_checker: MTProtoSettableUsernameChecker) -> None:
        self.fragment_checker = fragment_checker
        self.mtproto_checker = mtproto_checker

    async def start(self) -> None:
        await self.mtproto_checker.start()

    async def close(self) -> None:
        await self.mtproto_checker.close()

    async def is_available(self, username: str) -> bool:
        fragment_ok = await self.fragment_checker.is_available(username)
        if not fragment_ok:
            return False
        return await self.mtproto_checker.is_available(username)


def _has_mtproto_credentials(settings: Settings) -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_STRING_SESSION)


def _build_mtproto_checker(settings: Settings) -> MTProtoSettableUsernameChecker:
    if not _has_mtproto_credentials(settings):
        raise RuntimeError(
            "Strict username checking requires TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION"
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
        logger.warning("USERNAME_CHECK_MODE=mock is enabled. Use only for local tests.")
        return MockUsernameChecker()

    if _has_mtproto_credentials(settings):
        # Always prefer MTProto when credentials are present. This avoids old
        # Railway env values like USERNAME_CHECK_MODE=fragment causing false positives.
        logger.info("Using strict MTProto account.checkUsername checker")
        return _build_mtproto_checker(settings)

    reason = (
        "MTProto credentials are missing. Set USERNAME_CHECK_MODE=mtproto, "
        "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION. "
        "Fragment/BotAPI/HTTP modes are disabled in production because they can "
        "return occupied usernames such as roman or angel as free."
    )
    return FailClosedUsernameChecker(reason)


async def is_username_available(
    username: str,
    *,
    checker: UsernameCheckerAdapter,
    redis: Redis | None = None,
    cache_ttl: int = 120,
) -> bool:
    username = username.lower().lstrip("@")
    if not is_valid_username(username):
        return False

    # v4 drops all old false-positive cache records from previous checkers.
    cache_key = f"prime_nick:username:v5:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        # Positive availability changes quickly; keep it short. Negative can be
        # longer, but one key is enough for now.
        await redis.set(cache_key, "1" if available else "0", ex=cache_ttl)
    return available
