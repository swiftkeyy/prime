from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from aiogram.types import Update

router = APIRouter()


@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, bool]:
    settings = request.app.state.settings
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if settings.WEBHOOK_SECRET and secret != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    data = await request.json()
    bot = request.app.state.bot
    dp = request.app.state.dp
    update = Update.model_validate(data, context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}
