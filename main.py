from __future__ import annotations

import asyncio
import logging
import os

import uvicorn

from config import get_settings
from loader import create_runtime
from services.username_stock_worker import username_stock_worker
from web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("prime_nick")

settings = get_settings()
bot, dp, redis, engine, sessionmaker, username_checker = create_runtime(settings)
stock_worker_task: asyncio.Task | None = None
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
    checker_start = getattr(username_checker, "start", None)
    if checker_start:
        await checker_start()

    global stock_worker_task
    if settings.USERNAME_STOCK_ENABLED and settings.USERNAME_STOCK_WORKER_ENABLED:
        stock_worker_task = asyncio.create_task(
            username_stock_worker(
                sessionmaker=sessionmaker,
                settings=settings,
                username_checker=username_checker,
                redis=redis,
            )
        )
        logger.info("Username stock worker scheduled")

    await bot.set_webhook(
        settings.webhook_url,
        secret_token=settings.WEBHOOK_SECRET or None,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    logger.info("Telegram webhook set: %s", settings.webhook_url)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global stock_worker_task
    if stock_worker_task is not None:
        stock_worker_task.cancel()
        try:
            await stock_worker_task
        except asyncio.CancelledError:
            pass

    checker_close = getattr(username_checker, "close", None)
    if checker_close:
        await checker_close()

    await dp.storage.close()
    await bot.session.close()
    await redis.aclose()
    await engine.dispose()
    logger.info("PRIME NICK shutdown complete")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", settings.PORT)), proxy_headers=True)
