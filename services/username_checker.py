from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass, field
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
    """Telegram temporarily rate-limited all available checker accounts."""

    def __init__(self, retry_after: int = 0) -> None:
        self.retry_after = max(0, int(retry_after or 0))
        super().__init__(f"Telegram username check is rate-limited for {self.retry_after} seconds")


class UsernameCheckerAdapter(Protocol):
    async def is_available(self, username: str) -> bool: ...


class MockUsernameChecker:
    async def start(self) -> None:
        logger.warning("USERNAME_CHECK_MODE=mock is enabled. Use only for local tests.")

    async def close(self) -> None:
        return None

    async def is_available(self, username: str) -> bool:
        await asyncio.sleep(0.05)
        return random.random() < 0.18


class FailClosedUsernameChecker:
    """Never returns false positives when production checker is not configured."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def start(self) -> None:
        logger.error("Username checker is disabled: %s", self.reason)

    async def close(self) -> None:
        return None

    async def is_available(self, username: str) -> bool:
        logger.error("Username check refused for @%s: %s", username, self.reason)
        raise UsernameCheckerNotConfigured(self.reason)


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


@dataclass
class MTProtoAccountSlot:
    index: int
    string_session: str
    api_id: int
    api_hash: str
    timeout: int
    delay_seconds: float
    max_cooldown_seconds: int
    client: object | None = None
    started: bool = False
    disabled: bool = False
    own_username: str | None = None
    cooldown_until: float = 0.0
    last_request: float = 0.0
    start_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    request_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def now(self) -> float:
        return asyncio.get_event_loop().time()

    def retry_after(self) -> int:
        return max(0, int(self.cooldown_until - self.now()))

    def is_cooling_down(self) -> bool:
        return self.retry_after() > 0

    async def start(self) -> None:
        async with self.start_lock:
            if self.started or self.disabled:
                return

            try:
                from telethon import TelegramClient
                from telethon.sessions import StringSession
            except ImportError as exc:
                self.disabled = True
                raise UsernameCheckerNotConfigured("telethon is not installed. Add telethon to requirements.txt") from exc

            try:
                self.client = TelegramClient(
                    StringSession(self.string_session.strip()),
                    self.api_id,
                    self.api_hash,
                    sequential_updates=True,
                    connection_retries=2,
                    request_retries=0,
                    timeout=self.timeout,
                    flood_sleep_threshold=0,
                )
                await self.client.connect()  # type: ignore[union-attr]
                if not await self.client.is_user_authorized():  # type: ignore[union-attr]
                    raise UsernameCheckerNotConfigured("session is not authorized")
                me = await self.client.get_me()  # type: ignore[union-attr]
                self.own_username = (getattr(me, "username", None) or "").lower() or None
                self.started = True
                logger.info("MTProto pool account #%s connected own_username=%s", self.index, self.own_username or "none")
            except Exception as exc:
                self.disabled = True
                logger.error("MTProto pool account #%s disabled: %s: %s", self.index, exc.__class__.__name__, str(exc)[:180])
                try:
                    if self.client is not None:
                        await self.client.disconnect()  # type: ignore[union-attr]
                except Exception:
                    pass
                self.client = None
                raise

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()  # type: ignore[union-attr]
            except Exception as exc:
                logger.warning("MTProto pool account #%s disconnect failed: %s", self.index, exc.__class__.__name__)
        self.started = False

    async def _sleep_for_rate_limit(self) -> None:
        now = self.now()
        wait_for = self.delay_seconds - (now - self.last_request)
        if wait_for > 0:
            await asyncio.sleep(wait_for)
        self.last_request = self.now()

    def _put_on_cooldown(self, seconds: int) -> None:
        seconds = max(1, int(seconds or 1))
        cooldown = min(seconds, self.max_cooldown_seconds)
        self.cooldown_until = self.now() + cooldown
        logger.warning(
            "MTProto account #%s cooldown: telegram_retry_after=%s local_cooldown=%s",
            self.index,
            seconds,
            cooldown,
        )

    async def check_username(self, username: str) -> bool:
        if self.disabled:
            raise UsernameCheckerNotConfigured(f"MTProto account #{self.index} is disabled")
        if not self.started:
            await self.start()
        if self.is_cooling_down():
            raise UsernameCheckerRateLimited(self.retry_after())
        if self.own_username and username == self.own_username:
            logger.info("MTProto pool account #%s @%s -> own username, skip", self.index, username)
            return False

        async with self.request_lock:
            if self.is_cooling_down():
                raise UsernameCheckerRateLimited(self.retry_after())
            await self._sleep_for_rate_limit()

            try:
                from telethon.errors import FloodWaitError, RPCError
                from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameOccupiedError
                from telethon.tl.functions.account import CheckUsernameRequest
            except ImportError as exc:
                raise UsernameCheckerNotConfigured("telethon import error") from exc

            try:
                result = await asyncio.wait_for(
                    self.client(CheckUsernameRequest(username), flood_sleep_threshold=0),  # type: ignore[misc,operator]
                    timeout=self.timeout,
                )
                allowed = bool(result)
                logger.info(
                    "MTProto pool account #%s account.checkUsername @%s -> %s",
                    self.index,
                    username,
                    "settable" if allowed else "not settable",
                )
                return allowed

            except (UsernameInvalidError, UsernameOccupiedError):
                logger.info("MTProto pool account #%s account.checkUsername @%s -> invalid/occupied", self.index, username)
                return False

            except FloodWaitError as exc:
                seconds = int(getattr(exc, "seconds", 0) or 0)
                self._put_on_cooldown(seconds)
                raise UsernameCheckerRateLimited(seconds)

            except asyncio.TimeoutError:
                logger.warning("MTProto pool account #%s checkUsername timeout @%s; candidate rejected", self.index, username)
                return False

            except RPCError as exc:
                msg = f"{exc.__class__.__name__} {str(exc)}".lower()
                blocked_markers = (
                    "username_invalid", "username_occupied", "username_purchase_available",
                    "purchase_available", "username_not_available", "not available",
                    "occupied", "invalid", "premium", "collectible", "reserved", "auction",
                )
                if any(marker in msg for marker in blocked_markers):
                    logger.info("MTProto pool account #%s checkUsername @%s -> blocked: %s", self.index, username, exc.__class__.__name__)
                    return False
                logger.warning("MTProto pool account #%s RPC error @%s: %s", self.index, username, msg[:180])
                return False

            except Exception as exc:
                logger.warning(
                    "MTProto pool account #%s unexpected error @%s: %s: %s",
                    self.index,
                    username,
                    exc.__class__.__name__,
                    str(exc)[:180],
                )
                return False


class MTProtoAccountPoolUsernameChecker:
    """Strict username checker with a pool of MTProto accounts.

    One Telegram account cannot handle production scanning: account.checkUsername
    is heavily rate-limited. This pool lets the owner add several StringSessions
    once and the bot will rotate them automatically. Flooded sessions are put on
    cooldown; the bot never falls back to Fragment/BotAPI and never returns
    unchecked usernames.
    """

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        string_sessions: list[str],
        timeout: int,
        delay_seconds: float,
        max_cooldown_seconds: int,
    ) -> None:
        if not api_id or not api_hash or not string_sessions:
            raise UsernameCheckerNotConfigured(
                "MTProto credentials are missing. Set TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSIONS."
            )
        self.api_id = int(api_id)
        self.api_hash = api_hash.strip()
        self.timeout = int(timeout)
        self.delay_seconds = max(1.5, float(delay_seconds))
        self.max_cooldown_seconds = max(60, int(max_cooldown_seconds))
        self.slots = [
            MTProtoAccountSlot(
                index=index + 1,
                string_session=session,
                api_id=self.api_id,
                api_hash=self.api_hash,
                timeout=self.timeout,
                delay_seconds=self.delay_seconds,
                max_cooldown_seconds=self.max_cooldown_seconds,
            )
            for index, session in enumerate(string_sessions)
        ]
        self._start_lock = asyncio.Lock()
        self._rr_lock = asyncio.Lock()
        self._rr_index = 0
        self._started = False

    async def start(self) -> None:
        async with self._start_lock:
            if self._started:
                return

            ok = 0
            for slot in self.slots:
                try:
                    await slot.start()
                    ok += 1
                except Exception:
                    continue

            if ok <= 0:
                raise UsernameCheckerNotConfigured(
                    "No MTProto accounts connected. Regenerate sessions with scripts/create_telethon_session.py"
                )

            self._started = True
            logger.info("MTProto username checker pool ready: %s/%s accounts connected", ok, len(self.slots))

    async def close(self) -> None:
        for slot in self.slots:
            await slot.close()
        self._started = False
        logger.info("MTProto username checker pool disconnected")

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    async def _pick_slot(self) -> MTProtoAccountSlot | None:
        async with self._rr_lock:
            active_slots = [slot for slot in self.slots if not slot.disabled and slot.started]
            if not active_slots:
                return None

            n = len(active_slots)
            start = self._rr_index % n

            # Prefer accounts not currently cooling down and not already busy.
            for prefer_free_lock in (True, False):
                for offset in range(n):
                    idx = (start + offset) % n
                    slot = active_slots[idx]
                    if slot.is_cooling_down():
                        continue
                    if prefer_free_lock and slot.request_lock.locked():
                        continue
                    self._rr_index = idx + 1
                    return slot
            return None

    def _min_retry_after(self) -> int:
        retries = [slot.retry_after() for slot in self.slots if not slot.disabled and slot.retry_after() > 0]
        return min(retries) if retries else 60

    async def is_available(self, username: str) -> bool:
        username = username.lower().lstrip("@")
        if not is_valid_username(username):
            return False
        if username in KNOWN_BAD_USERNAMES:
            logger.info("MTProto pool @%s -> blocked by local known-bad list", username)
            return False

        await self._ensure_started()

        last_rate_limit: UsernameCheckerRateLimited | None = None
        attempts = max(1, len(self.slots))
        for _ in range(attempts):
            slot = await self._pick_slot()
            if slot is None:
                break
            try:
                return await slot.check_username(username)
            except UsernameCheckerRateLimited as exc:
                last_rate_limit = exc
                continue
            except UsernameCheckerNotConfigured:
                continue

        retry_after = last_rate_limit.retry_after if last_rate_limit else self._min_retry_after()
        logger.warning("MTProto pool exhausted; all accounts are cooling down retry_after=%s", retry_after)
        raise UsernameCheckerRateLimited(retry_after)


# Backwards-compatible names from earlier builds.
MTProtoStrictUsernameChecker = MTProtoAccountPoolUsernameChecker
MTProtoResolveUsernameChecker = MTProtoAccountPoolUsernameChecker
MTProtoSettableUsernameChecker = MTProtoAccountPoolUsernameChecker


def _parse_mtproto_sessions(settings: Settings) -> list[str]:
    raw = getattr(settings, "TELEGRAM_STRING_SESSIONS", "") or ""
    if not raw.strip():
        raw = getattr(settings, "TELEGRAM_STRING_SESSION", "") or ""
    # Railway can store this as one line separated by comma/semicolon or as a multiline variable.
    parts = re.split(r"[\n;,]+", raw)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        session = part.strip().strip('"').strip("'")
        if session and session not in seen:
            result.append(session)
            seen.add(session)
    return result


def _has_mtproto_credentials(settings: Settings) -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and _parse_mtproto_sessions(settings))


def _build_mtproto_checker(settings: Settings) -> MTProtoAccountPoolUsernameChecker:
    sessions = _parse_mtproto_sessions(settings)
    if not _has_mtproto_credentials(settings):
        raise UsernameCheckerNotConfigured(
            "MTProto credentials are missing. Set USERNAME_CHECK_MODE=mtproto, "
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSIONS."
        )
    return MTProtoAccountPoolUsernameChecker(
        api_id=settings.TELEGRAM_API_ID,
        api_hash=settings.TELEGRAM_API_HASH,
        string_sessions=sessions,
        timeout=settings.USERNAME_CHECK_TIMEOUT,
        delay_seconds=settings.MTPROTO_CHECK_DELAY_SECONDS,
        max_cooldown_seconds=getattr(settings, "MTPROTO_SESSION_MAX_COOLDOWN_SECONDS", 86400),
    )


def build_checker(settings: Settings) -> UsernameCheckerAdapter:
    mode = settings.USERNAME_CHECK_MODE
    logger.info("PRIME NICK username checker mode from env: %s", mode)

    if mode == "mock":
        return MockUsernameChecker()

    if _has_mtproto_credentials(settings):
        sessions_count = len(_parse_mtproto_sessions(settings))
        logger.info("Using MTProto username checker pool: %s configured account(s)", sessions_count)
        return _build_mtproto_checker(settings)

    reason = (
        "Strict username checking is not configured. Set TELEGRAM_API_ID, "
        "TELEGRAM_API_HASH and TELEGRAM_STRING_SESSIONS in Railway Variables. "
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

    # v12 introduces MTProto account pool. Do not reuse old false-positive cache.
    cache_key = f"prime_nick:username:v12:{username}"
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
