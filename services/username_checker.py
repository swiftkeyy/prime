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


class TelegramBotApiUsernameChecker(RateLimiterMixin):
    """Fallback checker.

    Bot API cannot reliably resolve arbitrary personal usernames. It is kept only
    as a fallback for channels/groups and for installations where MTProto is not
    configured. Production availability checks should use MTProtoUsernameChecker.
    """

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

        logger.warning(
            "telegram bot api checker unexpected response for username=%s code=%s description=%s",
            username,
            error_code,
            description[:120],
        )
        raise UsernameCheckError("telegram bot api unexpected response")


class MTProtoUsernameChecker(RateLimiterMixin):
    """Strict Telegram username resolver through MTProto.

    This is the correct production check for regular Telegram usernames.
    If contacts.resolveUsername returns a user/chat/channel -> username is taken.
    If Telegram returns UsernameNotOccupiedError -> username is not attached to
    an active Telegram account/channel at this moment.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        string_session: str,
        timeout: int = 7,
        delay_seconds: float = 0.8,
    ) -> None:
        super().__init__(delay_seconds=delay_seconds)
        self.api_id = api_id
        self.api_hash = api_hash
        self.string_session = string_session
        self.timeout = timeout
        self._client = None
        self._started = False
        self._start_lock = asyncio.Lock()

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
            self._started = True
            logger.info("MTProto username checker connected")

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
            from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameNotOccupiedError
            from telethon.tl.functions.contacts import ResolveUsernameRequest
        except ImportError as exc:
            raise UsernameCheckError("telethon import error") from exc

        try:
            await asyncio.wait_for(self._client(ResolveUsernameRequest(username)), timeout=self.timeout)  # type: ignore[misc]
            return False
        except UsernameNotOccupiedError:
            return True
        except UsernameInvalidError:
            return False
        except FloodWaitError as exc:
            logger.warning("mtproto checker flood wait: %s seconds", getattr(exc, "seconds", "unknown"))
            raise UsernameCheckError("mtproto flood wait") from exc
        except asyncio.TimeoutError as exc:
            raise UsernameCheckError("mtproto timeout") from exc
        except RPCError as exc:
            message = str(exc).lower()
            if "username_not_occupied" in message or "not occupied" in message:
                return True
            if "username_invalid" in message or "invalid" in message:
                return False
            logger.warning("mtproto checker rpc error for username=%s: %s", username, exc.__class__.__name__)
            raise UsernameCheckError("mtproto rpc error") from exc
        except Exception as exc:
            logger.warning("mtproto checker unexpected error for username=%s: %s", username, exc.__class__.__name__)
            raise UsernameCheckError("mtproto unexpected error") from exc


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
            logger.warning("username checker network error: %s", exc.__class__.__name__)
            raise UsernameCheckError("network error") from exc

        if response.status_code == 404:
            return True
        if response.status_code in {200, 301, 302, 303, 307, 308}:
            text = response.text.lower()
            if "tgme_username_link" in text or "telegram.me/" in text or "property=\"og:title\"" in text:
                return False
            return "username" in text and "not found" in text
        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"temporary status {response.status_code}")
        return False


class FragmentUsernameChecker(RateLimiterMixin):
    """Fragment-side guard for collectible, auction, sold and reserved usernames."""

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
            logger.warning("fragment checker network error: %s", exc.__class__.__name__)
            raise UsernameCheckError("fragment network error") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"fragment temporary status {response.status_code}")
        if response.status_code != 200:
            logger.warning("fragment checker unexpected status: %s", response.status_code)
            raise UsernameCheckError(f"fragment unexpected status {response.status_code}")

        try:
            payload = response.json()
        except ValueError:
            markup = response.text
        else:
            markup = str(payload.get("h") or payload.get("html") or payload)

        if self._is_blocked_by_fragment(markup):
            return False

        return True


class StrictFragmentTelegramUsernameChecker:
    """Fragment first, strict Telegram resolver second."""

    def __init__(self, fragment_checker: FragmentUsernameChecker, telegram_checker: UsernameCheckerAdapter) -> None:
        self.fragment_checker = fragment_checker
        self.telegram_checker = telegram_checker

    async def start(self) -> None:
        start = getattr(self.telegram_checker, "start", None)
        if start:
            await start()

    async def close(self) -> None:
        close = getattr(self.telegram_checker, "close", None)
        if close:
            await close()

    async def is_available(self, username: str) -> bool:
        fragment_ok = await self.fragment_checker.is_available(username)
        if not fragment_ok:
            return False
        return await self.telegram_checker.is_available(username)


def _build_mtproto_checker(settings: Settings) -> MTProtoUsernameChecker:
    if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH or not settings.TELEGRAM_STRING_SESSION:
        raise RuntimeError(
            "USERNAME_CHECK_MODE=mtproto requires TELEGRAM_API_ID, "
            "TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION"
        )
    return MTProtoUsernameChecker(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        string_session=settings.TELEGRAM_STRING_SESSION,
        timeout=settings.USERNAME_CHECK_TIMEOUT,
        delay_seconds=settings.MTPROTO_CHECK_DELAY_SECONDS,
    )


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    if settings.USERNAME_CHECK_MODE == "mock":
        return MockUsernameChecker()

    if settings.USERNAME_CHECK_MODE == "mtproto":
        return StrictFragmentTelegramUsernameChecker(
            FragmentUsernameChecker(
                timeout=settings.USERNAME_CHECK_TIMEOUT,
                delay_seconds=settings.FRAGMENT_CHECK_DELAY_SECONDS,
            ),
            _build_mtproto_checker(settings),
        )

    if settings.USERNAME_CHECK_MODE == "fragment":
        # Backward compatible mode. If MTProto env is configured, use it. If not,
        # fall back to Bot API and log a clear warning because Bot API can miss
        # occupied personal usernames like @roman.
        fragment = FragmentUsernameChecker(
            timeout=settings.USERNAME_CHECK_TIMEOUT,
            delay_seconds=settings.FRAGMENT_CHECK_DELAY_SECONDS,
        )
        if settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_STRING_SESSION:
            return StrictFragmentTelegramUsernameChecker(fragment, _build_mtproto_checker(settings))
        logger.warning(
            "USERNAME_CHECK_MODE=fragment without MTProto credentials uses Bot API fallback; "
            "regular personal usernames may be false positives. Set USERNAME_CHECK_MODE=mtproto."
        )
        return StrictFragmentTelegramUsernameChecker(
            fragment,
            TelegramBotApiUsernameChecker(
                bot_token=settings.BOT_TOKEN,
                timeout=settings.USERNAME_CHECK_TIMEOUT,
            ),
        )

    if settings.USERNAME_CHECK_MODE == "http":
        return TMeHttpUsernameChecker(timeout=settings.USERNAME_CHECK_TIMEOUT)

    return TelegramBotApiUsernameChecker(bot_token=settings.BOT_TOKEN, timeout=settings.USERNAME_CHECK_TIMEOUT)


async def is_username_available(
    username: str,
    *,
    checker: UsernameCheckerAdapter,
    redis: Redis | None = None,
    cache_ttl: int = 180,
) -> bool:
    username = username.lower().lstrip("@")
    if not is_valid_username(username):
        return False

    # v3 bypasses old Redis records that could contain false positives from
    # previous Fragment/Bot-API-only checkers.
    cache_key = f"prime_nick:username:v3:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        await redis.set(cache_key, "1" if available else "0", ex=cache_ttl)
    return available
