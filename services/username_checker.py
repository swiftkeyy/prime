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
        # Do not let Railway env accidentally spam Telegram. 0.35 sec is still fast
        # enough for UX, but much safer than bursts.
        self.delay_seconds = max(0.75, float(delay_seconds))
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def _rate_limit(self) -> None:
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = self.delay_seconds - (now - self._last_request)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request = asyncio.get_event_loop().time()


# Words that Telegram often keeps occupied/reserved/collectible or that are known
# bad fits for automatic output. This list protects UX from famous false hopes.
KNOWN_BAD_USERNAMES = {
    # Telegram/system/service words
    "admin", "administrator", "support", "telegram", "settings", "username",
    "login", "help", "owner", "moderator", "security", "premium", "fragment",
    "wallet", "crypto", "stars", "store", "bot", "bots", "api", "web",
    # Common short words and names that resolveUsername may mark as not occupied,
    # while Telegram UI still refuses to set them because they are reserved, sold,
    # collectible, protected or otherwise not assignable.
    "angel", "roman", "dobro", "zapor", "apple", "music", "money", "video",
    "cloud", "world", "super", "queen", "joker", "magic", "prime",
    "kvant", "novak", "sever", "orbit", "karat", "liver", "total", "lumen",
    "miron", "veter", "sonar", "nolan", "vital", "kredo", "nevan", "solen",
    "moral", "davor", "levin", "radon", "zoran", "valor", "raven", "rival",
    "venom", "vesta", "dorin", "buran", "lunar", "sokol", "volna", "iskra",
}


class MTProtoResolveUsernameChecker(RateLimiterMixin):
    """No-flood MTProto checker for production search.

    Telegram's account.checkUsername is the only method that answers "can THIS
    account set this username", but it has a very aggressive flood limit. In the
    previous build it received FloodWaitError for 70k+ seconds after only a few
    checks, so it cannot be used inside live scans.

    The production pipeline is deliberately fail-closed:
    1. contacts.resolveUsername filters usernames that are already assigned to
       a user/channel/chat;
    2. account.checkUsername performs the final Telegram UI-style check, so
       reserved/collectible/protected words like @kvant, @novak, @sever do not
       leak into results;
    3. if Telegram rate-limits the strict final check, the candidate is skipped
       instead of being shown to the user.

    This gives fewer results for 5-symbol scans, but avoids fake usernames.
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
        self._resolve_flood_until = 0.0
        self._final_flood_until = 0.0

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
            logger.info("MTProto strict username checker connected own_username=%s", self._own_username or "none")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
        self._started = False
        logger.info("MTProto username checker disconnected")

    async def _ensure_started(self) -> None:
        if not self._started:
            await self.start()

    async def _final_settable_check(self, username: str) -> bool:
        """Final strict check: would Telegram allow this username on this account?

        resolveUsername only says that nobody currently owns the username. It
        does not catch many Telegram-side restrictions. account.checkUsername
        is rate-limited, so every error/flood is fail-closed: no username is
        shown unless this method returns True.
        """
        now = asyncio.get_event_loop().time()
        if now < self._final_flood_until:
            logger.warning("MTProto final check cooldown active, skip @%s", username)
            return False

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
            cooldown = min(max(seconds, 60), 3600)
            self._final_flood_until = asyncio.get_event_loop().time() + cooldown
            logger.warning(
                "MTProto account.checkUsername flood wait @%s: %s sec; cooldown=%s sec; candidate rejected",
                username,
                seconds,
                cooldown,
            )
            return False

        except asyncio.TimeoutError:
            logger.warning("MTProto account.checkUsername timeout for @%s; candidate rejected", username)
            return False

        except RPCError as exc:
            msg = f"{exc.__class__.__name__} {str(exc)}".lower()
            blocked_markers = (
                "username_invalid",
                "username_occupied",
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
            if any(marker in msg for marker in blocked_markers):
                logger.info("MTProto account.checkUsername @%s -> blocked: %s", username, exc.__class__.__name__)
                return False
            logger.warning("MTProto account.checkUsername RPC error @%s: %s", username, msg[:180])
            return False

        except Exception as exc:
            logger.warning("MTProto account.checkUsername unexpected error @%s: %s: %s", username, exc.__class__.__name__, str(exc)[:180])
            return False


    async def is_available(self, username: str) -> bool:
        username = username.lower().lstrip("@")
        if not is_valid_username(username):
            return False

        if username in KNOWN_BAD_USERNAMES:
            logger.info("MTProto resolveUsername @%s -> blocked by local known-bad list", username)
            return False

        await self._ensure_started()

        if self._own_username and username == self._own_username:
            logger.info("MTProto resolveUsername @%s -> own username, skip", username)
            return False

        now = asyncio.get_event_loop().time()
        if now < self._resolve_flood_until:
            # Do not raise and do not show the scary unavailable message for every
            # user. Just skip this candidate while Telegram cooldown is active.
            logger.warning("MTProto resolve cooldown active, skip @%s", username)
            return False

        await self._rate_limit()

        try:
            from telethon.errors import FloodWaitError, RPCError
            from telethon.errors.rpcerrorlist import UsernameInvalidError, UsernameNotOccupiedError
            from telethon.tl.functions.contacts import ResolveUsernameRequest
        except ImportError as exc:
            raise UsernameCheckerNotConfigured("telethon import error") from exc

        try:
            # Telethon accepts flood_sleep_threshold on the client call, not on
            # asyncio.wait_for. Passing it to wait_for caused TypeError and made
            # every candidate fail. Keep timeout outside and disable auto-sleep
            # inside Telethon call so FloodWaitError is raised immediately.
            request = ResolveUsernameRequest(username)
            await asyncio.wait_for(
                self._client(request, flood_sleep_threshold=0),  # type: ignore[misc]
                timeout=self.timeout,
            )
            logger.info("MTProto resolveUsername @%s -> occupied", username)
            return False

        except UsernameNotOccupiedError:
            logger.info("MTProto resolveUsername @%s -> not occupied; running strict final check", username)
            return await self._final_settable_check(username)

        except UsernameInvalidError:
            logger.info("MTProto resolveUsername @%s -> invalid", username)
            return False

        except FloodWaitError as exc:
            seconds = int(getattr(exc, "seconds", 0) or 0)
            cooldown = min(max(seconds, 30), 600)
            self._resolve_flood_until = asyncio.get_event_loop().time() + cooldown
            logger.warning(
                "MTProto resolve flood wait while checking @%s: %s sec; cooldown=%s sec",
                username,
                seconds,
                cooldown,
            )
            return False

        except asyncio.TimeoutError:
            logger.warning("MTProto resolve timeout for @%s; candidate skipped", username)
            return False

        except RPCError as exc:
            message = f"{exc.__class__.__name__} {str(exc)}".lower()
            blocked_markers = (
                "username_invalid",
                "username_occupied",
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
                logger.info("MTProto resolveUsername @%s -> not usable: %s", username, exc.__class__.__name__)
                return False
            logger.warning("MTProto resolve RPC error for @%s: %s", username, message[:180])
            return False

        except Exception as exc:
            logger.warning("MTProto resolve unexpected error for @%s: %s: %s", username, exc.__class__.__name__, str(exc)[:180])
            return False


# Backwards-compatible name: other modules may import this class from older builds.
MTProtoSettableUsernameChecker = MTProtoResolveUsernameChecker


def _has_mtproto_credentials(settings: Settings) -> bool:
    return bool(settings.TELEGRAM_API_ID and settings.TELEGRAM_API_HASH and settings.TELEGRAM_STRING_SESSION)


def _build_mtproto_checker(settings: Settings) -> MTProtoResolveUsernameChecker:
    if not _has_mtproto_credentials(settings):
        raise UsernameCheckerNotConfigured(
            "MTProto credentials are missing. Set USERNAME_CHECK_MODE=mtproto, "
            "TELEGRAM_API_ID, TELEGRAM_API_HASH and TELEGRAM_STRING_SESSION."
        )
    return MTProtoResolveUsernameChecker(
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
        logger.info("Using MTProto resolveUsername + strict account.checkUsername final checker")
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

    # v10 adds strict account.checkUsername final verification and drops resolve-only cache.
    cache_key = f"prime_nick:username:v10:{username}"
    if redis:
        cached = await redis.get(cache_key)
        if cached is not None:
            if isinstance(cached, bytes):
                cached = cached.decode()
            return cached == "1"

    available = await checker.is_available(username)
    if redis:
        # Free usernames can be taken any second; keep positive cache very short.
        await redis.set(cache_key, "1" if available else "0", ex=positive_ttl if available else negative_ttl)
    return available
