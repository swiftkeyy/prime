from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from redis.asyncio import Redis

from config import Settings
from services.username_score import rarity_line

logger = logging.getLogger(__name__)

SUBSCRIBERS_KEY = "prime_nick:drop_alerts:subscribers"
QUEUE_KEY = "prime_nick:drop_alerts:queue"
SEEN_PREFIX = "prime_nick:drop_alerts:seen:"
COOLDOWN_PREFIX = "prime_nick:drop_alerts:cooldown:"
DIGEST_PREFIX = "prime_nick:drop_alerts:digest:"


async def subscribe_drop_alerts(redis: Redis, telegram_id: int) -> None:
    await redis.sadd(SUBSCRIBERS_KEY, str(telegram_id))


async def unsubscribe_drop_alerts(redis: Redis, telegram_id: int) -> None:
    await redis.srem(SUBSCRIBERS_KEY, str(telegram_id))


async def is_subscribed_to_drop_alerts(redis: Redis, telegram_id: int) -> bool:
    return bool(await redis.sismember(SUBSCRIBERS_KEY, str(telegram_id)))


async def enqueue_drop_alert(redis: Redis, username: str) -> None:
    username = username.lower().lstrip("@")
    seen_key = f"{SEEN_PREFIX}{username}"
    if await redis.set(seen_key, "1", nx=True, ex=3600):
        await redis.rpush(QUEUE_KEY, username)


def drop_alert_text(usernames: list[str]) -> str:
    cleaned = [item.lstrip("@") for item in usernames if item]
    lines = [f"• @{raw} · {rarity_line(raw)}" for raw in cleaned]
    title = "🔥 <b>Новые дропы PRIME NICK</b>" if len(cleaned) > 1 else "🔥 <b>Новый дроп PRIME NICK</b>"
    return title + "\n\nВ витрине появились свежие username:\n\n" + "\n".join(lines) + "\n\nОткрой бота и забирай сильные варианты, пока они не ушли другим."


def _unique_usernames(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        username = value.lower().lstrip("@")
        if username and username not in seen:
            seen.add(username)
            result.append(username)
        if len(result) >= limit:
            break
    return result


async def drop_alerts_worker(bot: Bot, redis: Redis, settings: Settings) -> None:
    if not settings.DROP_ALERTS_ENABLED:
        logger.info("Drop alerts worker disabled")
        return

    logger.info("Drop alerts worker started interval=%ss", settings.DROP_ALERTS_INTERVAL_SECONDS)
    while True:
        try:
            usernames: list[str] = []
            for _ in range(max(1, settings.DROP_ALERTS_BATCH_SIZE)):
                value = await redis.lpop(QUEUE_KEY)
                if not value:
                    break
                usernames.append(str(value))

            if not usernames:
                await asyncio.sleep(max(10, settings.DROP_ALERTS_INTERVAL_SECONDS))
                continue

            subscribers = [int(item) for item in await redis.smembers(SUBSCRIBERS_KEY)]
            if not subscribers:
                await asyncio.sleep(1)
                continue

            digest_usernames = _unique_usernames(usernames, max(1, settings.DROP_ALERTS_DIGEST_SIZE))
            if not digest_usernames:
                await asyncio.sleep(1)
                continue

            digest_id = ",".join(digest_usernames)
            text = drop_alert_text(digest_usernames)
            for telegram_id in subscribers:
                cooldown_key = f"{COOLDOWN_PREFIX}{telegram_id}"
                digest_key = f"{DIGEST_PREFIX}{telegram_id}:{digest_id}"
                if await redis.exists(cooldown_key):
                    continue
                if await redis.exists(digest_key):
                    continue
                try:
                    await bot.send_message(telegram_id, text)
                    await redis.set(cooldown_key, "1", ex=max(60, settings.DROP_ALERTS_USER_COOLDOWN_SECONDS))
                    await redis.set(digest_key, "1", ex=max(300, settings.DROP_ALERTS_USER_COOLDOWN_SECONDS * 2))
                except Exception as exc:
                    logger.warning("drop alert send failed user=%s error=%s", telegram_id, exc.__class__.__name__)

            await asyncio.sleep(max(5, settings.DROP_ALERTS_INTERVAL_SECONDS))
        except asyncio.CancelledError:
            logger.info("Drop alerts worker stopped")
            raise
        except Exception as exc:
            logger.exception("Drop alerts worker unexpected error: %s", exc.__class__.__name__)
            await asyncio.sleep(30)
