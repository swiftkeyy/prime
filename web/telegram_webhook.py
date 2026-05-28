from __future__ import annotations

import asyncio
import logging

from aiogram.types import Update
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()
logger = logging.getLogger(__name__)


async def process_update(request: Request, data: dict) -> None:
    bot = request.app.state.bot
    dp = request.app.state.dp
    try:
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:
        logger.exception("telegram webhook update processing failed")


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    settings = request.app.state.settings
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if settings.WEBHOOK_SECRET and secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    data = await request.json()
    asyncio.create_task(process_update(request, data))
    return {"ok": True}
