from __future__ import annotations

import asyncio
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import Settings
from services.drop_alerts import enqueue_drop_alert
from services.username_checker import UsernameCheckerAdapter, UsernameCheckerNotConfigured, UsernameCheckerRateLimited, is_username_available
from services.username_generator import generate_username
from services.username_stock import (
    count_available_stock,
    count_available_stock_matching,
    mark_username_rejected,
    release_expired_stock_holds,
    upsert_available_username,
)

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
    while True:
        try:
            async with sessionmaker() as session:
                await release_expired_stock_holds(session)
                await session.commit()

            targets = {
                5: settings.USERNAME_STOCK_MIN_5,
                6: settings.USERNAME_STOCK_MIN_6,
                7: settings.USERNAME_STOCK_MIN_7,
            }
            clean_five_target = max(2, targets[5] // 3)
            counts: dict[int, int] = {}
            clean_five_count = 0
            async with sessionmaker() as session:
                for item_length in (5, 6, 7):
                    counts[item_length] = await count_available_stock(session, item_length)
                clean_five_count = await count_available_stock_matching(
                    session,
                    5,
                    digits_enabled=False,
                    underscore_enabled=False,
                )
                await session.commit()

            deficits = {item_length: targets[item_length] - counts[item_length] for item_length in (5, 6, 7)}
            clean_five_deficit = clean_five_target - clean_five_count
            if max(deficits.values()) <= 0 and clean_five_deficit <= 0:
                logger.info(
                    "Username stock worker idle stock_5=%s stock_6=%s stock_7=%s clean_5=%s",
                    counts[5],
                    counts[6],
                    counts[7],
                    clean_five_count,
                )
                await asyncio.sleep(max(2.0, settings.USERNAME_STOCK_CHECK_INTERVAL_SECONDS))
                continue

            # Fill the emptiest bucket first. PRIME 5-symbol results are the most
            # visible feature, so ties prefer 5, then 6, then 7.
            if clean_five_deficit > 0:
                length = 5
            else:
                length = max((5, 6, 7), key=lambda item_length: (deficits[item_length], -item_length))

            # 5-char demand is split into two very different buckets:
            # clean usernames for users with digits OFF and mixed usernames for users
            # with digits ON. Warm both, otherwise the clean pool stays near-zero.
            if length == 5 and clean_five_deficit > 0:
                digits = False
                style_mode = "clean"
                logger.info("warming clean 5-char")
            else:
                digits = length == 5
                style_mode = "mixed" if digits else "clean"
                if length == 5:
                    logger.info("warming mixed 5-char")
                elif length == 6:
                    logger.info("warming 6-char")
                else:
                    logger.info("warming 7-char")

            candidate = generate_username(length, digits_enabled=digits, underscore_enabled=False, style_mode=style_mode)

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
                    await enqueue_drop_alert(redis, candidate)
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
