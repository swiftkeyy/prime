from __future__ import annotations

import asyncio
import logging
import random
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

    async def is_available(self, username: str) -> bool:
        # Tiny adapter-level rate limit. Real production may additionally use a dedicated queue.
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = 0.35 - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_event_loop().time()

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
            # Telegram sometimes returns a public landing page even for empty names.
            return "username" in text and "not found" in text
        if response.status_code in {429, 500, 502, 503, 504}:
            raise UsernameCheckError(f"temporary status {response.status_code}")
        return False


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    if settings.USERNAME_CHECK_MODE == "mock":
        return MockUsernameChecker()
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
