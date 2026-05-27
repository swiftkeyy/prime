from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import Settings
from services.username_checker import UsernameCheckerAdapter, UsernameCheckerNotConfigured, UsernameCheckerRateLimited, is_username_available
from services.username_generator import generate_username
from services.username_stock import count_available_stock, mark_username_rejected, release_expired_stock_holds, upsert_available_username

logger = logging.getLogger(__name__)


async def username_stock_worker(
    *,
    sessionmaker: async_sessionmaker,
    settings: Settings,
    username_checker: UsernameCheckerAdapter,
    redis: Redis,
) -> None:
    if not settings.USERNAME_STOCK_WORKER_ENABLED:
        logger.info("Username stock worker disabled")
        return

    logger.info(
        "Username stock worker started interval=%ss ttl=%sh live_check=%s",
        settings.USERNAME_STOCK_CHECK_INTERVAL_SECONDS,
        settings.USERNAME_STOCK_TTL_HOURS,
        settings.USERNAME_LIVE_CHECK_ENABLED,
    )
    lengths = [5, 6, 7]
    idx = 0

    while True:
        try:
            async with sessionmaker() as session:
                await release_expired_stock_holds(session)
                await session.commit()

            length = lengths[idx % len(lengths)]
            idx += 1
            target = {
                5: settings.USERNAME_STOCK_MIN_5,
                6: settings.USERNAME_STOCK_MIN_6,
                7: settings.USERNAME_STOCK_MIN_7,
            }[length]

            async with sessionmaker() as session:
                current = await count_available_stock(session, length)
                await session.commit()
            if current >= target:
                await asyncio.sleep(max(2.0, settings.USERNAME_STOCK_CHECK_INTERVAL_SECONDS))
                continue

            # Worker may use digits for 5 chars to build useful stock. Pure 5-letter
            # usernames are nearly impossible in 2026.
            digits = length == 5
            candidate = generate_username(length, digits_enabled=digits, underscore_enabled=False, style_mode="mixed" if digits else "clean")

            try:
                available = await is_username_available(candidate, checker=username_checker, redis=redis, positive_ttl=60, negative_ttl=1800)
            except UsernameCheckerRateLimited as exc:
                wait = min(max(exc.retry_after, 60), 1800)
                logger.warning("Username stock worker rate limited retry_after=%s; sleeping %ss", exc.retry_after, wait)
                await asyncio.sleep(wait)
                continue
            except UsernameCheckerNotConfigured:
                logger.error("Username stock worker stopped: checker is not configured")
                await asyncio.sleep(300)
                continue
            except Exception as exc:
                logger.warning("Username stock worker checker error for @%s: %s", candidate, exc.__class__.__name__)
                await asyncio.sleep(max(2.0, settings.USERNAME_STOCK_CHECK_INTERVAL_SECONDS))
                continue

            async with sessionmaker() as session:
                if available:
                    await upsert_available_username(session, candidate, settings=settings, source="worker")
                    logger.info("Username stock added @%s length=%s", candidate, length)
                else:
                    await mark_username_rejected(session, candidate, source="worker")
                await session.commit()

            await asyncio.sleep(max(2.0, settings.USERNAME_STOCK_CHECK_INTERVAL_SECONDS))

        except asyncio.CancelledError:
            logger.info("Username stock worker stopped")
            raise
        except Exception as exc:
            logger.exception("Username stock worker unexpected error: %s", exc.__class__.__name__)
            await asyncio.sleep(30)
