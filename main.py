from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from config import get_settings
from loader import create_runtime
from web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("prime_nick")

settings = get_settings()
bot, dp, redis, engine, sessionmaker, username_checker = create_runtime(settings)
app = create_app(
    bot=bot,
    dp=dp,
    settings=settings,
    sessionmaker=sessionmaker,
    redis=redis,
    engine=engine,
    username_checker=username_checker,
)


@app.on_event("startup")
async def on_startup() -> None:
    await bot.set_webhook(
        settings.webhook_url,
        secret_token=settings.WEBHOOK_SECRET or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info("Telegram webhook set: %s", settings.webhook_url)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("delete webhook failed: %s", exc.__class__.__name__)
    await dp.storage.close()
    await bot.session.close()
    await redis.aclose()
    await engine.dispose()
    logger.info("PRIME NICK shutdown complete")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", settings.PORT)), proxy_headers=True)
