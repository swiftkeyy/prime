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
    """Final Telegram-side guard against false positives.

    Fragment is good for collectible/auction/reserved usernames, but it may not
    reliably tell whether a regular @username is already attached to a Telegram
    account/channel. Bot API getChat is used as the final check:
      - getChat(@name) OK       -> username is taken
      - "chat not found"        -> not attached to a public Telegram entity

    A username is marked available only after Fragment does not block it AND
    getChat says that Telegram has no chat/user/channel with this username.
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
            logger.warning("telegram api checker network error: %s", exc.__class__.__name__)
            raise UsernameCheckError("telegram api network error") from exc

        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"telegram api temporary status {response.status_code}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise UsernameCheckError("telegram api invalid json") from exc

        if payload.get("ok") is True:
            return False

        description = str(payload.get("description", "")).lower()
        error_code = int(payload.get("error_code") or response.status_code or 0)

        if error_code == 400 and "chat not found" in description:
            return True

        # Treat everything ambiguous as temporary checker failure, not as a hit.
        logger.warning(
            "telegram api checker unexpected response for username=%s code=%s description=%s",
            username,
            error_code,
            description[:120],
        )
        raise UsernameCheckError("telegram api unexpected response")


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
            # Existing public users/channels usually have this OpenGraph block.
            if "tgme_username_link" in text or "telegram.me/" in text or "property=\"og:title\"" in text:
                return False
            return "username" in text and "not found" in text
        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"temporary status {response.status_code}")
        return False


class FragmentUsernameChecker(RateLimiterMixin):
    """Fragment-side guard for collectible, auction, sold and reserved usernames.

    Fragment has no stable public API. This adapter intentionally errs on the
    safe side: explicit Fragment hits are unavailable; ambiguous pages are passed
    to the Telegram Bot API guard by StrictFragmentTelegramUsernameChecker.
    """

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
            # Fragment often returns HTML in `h`. If it returns another JSON
            # shape, do NOT call it a hit; pass it to Telegram API guard.
            markup = str(payload.get("h") or payload.get("html") or payload)

        if self._is_blocked_by_fragment(markup):
            return False

        # No Fragment auction/collectible/reserved signal found. This is not
        # enough for a final "free" answer; Strict checker will verify via Bot API.
        return True


class StrictFragmentTelegramUsernameChecker:
    """Fragment first, Telegram Bot API second.

    This fixes false positives like @angel: Fragment can be ambiguous, while
    Telegram itself says the username is already occupied. The bot now returns
    a username only if both checks pass.
    """

    def __init__(self, fragment_checker: FragmentUsernameChecker, telegram_checker: TelegramBotApiUsernameChecker) -> None:
        self.fragment_checker = fragment_checker
        self.telegram_checker = telegram_checker

    async def is_available(self, username: str) -> bool:
        fragment_ok = await self.fragment_checker.is_available(username)
        if not fragment_ok:
            return False
        return await self.telegram_checker.is_available(username)


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    if settings.USERNAME_CHECK_MODE == "mock":
        return MockUsernameChecker()
    if settings.USERNAME_CHECK_MODE == "fragment":
        return StrictFragmentTelegramUsernameChecker(
            FragmentUsernameChecker(
                timeout=settings.USERNAME_CHECK_TIMEOUT,
                delay_seconds=settings.FRAGMENT_CHECK_DELAY_SECONDS,
            ),
            TelegramBotApiUsernameChecker(
                bot_token=settings.BOT_TOKEN,
                timeout=settings.USERNAME_CHECK_TIMEOUT,
            ),
        )
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

    # v2 bypasses old Redis records that could contain false positives from the
    # previous Fragment-only checker.
    cache_key = f"prime_nick:username:v2:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        await redis.set(cache_key, "1" if available else "0", ex=cache_ttl)
    return available
