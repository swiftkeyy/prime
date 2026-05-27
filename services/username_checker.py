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


class TMeHttpUsernameChecker:
    def __init__(self, timeout: int = 7) -> None:
        self.timeout = timeout
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _rate_limit(self, delay_seconds: float = 0.35) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = delay_seconds - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_event_loop().time()

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
            if "tgme_username_link" in text or "if you have <strong>telegram</strong>" in text:
                return False
            return "username" in text and "not found" in text
        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"temporary status {response.status_code}")
        return False


class FragmentUsernameChecker:
    """Checks username state through Fragment.

    Fragment does not provide a stable public API, so this adapter uses the same
    AJAX endpoint that the Fragment web interface calls. If Fragment changes the
    markup, the adapter raises UsernameCheckError instead of returning a fake hit.
    """

    BASE_URL = "https://fragment.com"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0 Safari/537.36 PRIME-NICK/1.0"
    )

    def __init__(self, timeout: int = 7, delay_seconds: float = 0.8) -> None:
        self.timeout = timeout
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

    @staticmethod
    def _extract_status(markup: str) -> str | None:
        text = markup.lower()
        match = re.search(r"tm-section-header-status\s+([^\"']+)", text)
        if match:
            return match.group(1).strip()
        for status in ("tm-status-taken", "tm-status-avail", "tm-status-unavail"):
            if status in text:
                return status
        return None

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

        markup = ""
        try:
            payload = response.json()
        except ValueError:
            markup = response.text
        else:
            # Fragment AJAX response usually contains HTML in `h`.
            # If `h` is absent, the username is treated as basic available.
            if "h" not in payload:
                return True
            markup = str(payload.get("h") or "")

        status = self._extract_status(markup)
        if status is None:
            # Plain HTML fallback. These pages are not free registration hits.
            text = markup.lower()
            if "telegram username" in text and ("sale price" in text or "bid history" in text or "owner" in text):
                return False
            logger.warning("fragment checker could not parse status for username=%s", username)
            raise UsernameCheckError("fragment parse error")

        # Fragment statuses:
        # taken      -> already used on Telegram, not free
        # avail      -> collectible auction/sale, not free registration
        # unavail    -> sold/unavailable, not free
        if "tm-status-taken" in status:
            return False
        if "tm-status-avail" in status:
            return False
        if "tm-status-unavail" in status:
            return False

        raise UsernameCheckError(f"fragment unknown status {status}")


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    if settings.USERNAME_CHECK_MODE == "mock":
        return MockUsernameChecker()
    if settings.USERNAME_CHECK_MODE == "fragment":
        return FragmentUsernameChecker(
            timeout=settings.USERNAME_CHECK_TIMEOUT,
            delay_seconds=settings.FRAGMENT_CHECK_DELAY_SECONDS,
        )
    return TMeHttpUsernameChecker(timeout=settings.USERNAME_CHECK_TIMEOUT)


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

    cache_key = f"prime_nick:username:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        await redis.set(cache_key, "1" if available else "0", ex=cache_ttl)
    return available
