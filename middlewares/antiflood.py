from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from redis.asyncio import Redis

from texts import ANTIFLOOD


class AntiFloodMiddleware(BaseMiddleware):
    def __init__(self, redis: Redis, ttl_ms: int = 850) -> None:
        self.redis = redis
        self.ttl_ms = ttl_ms

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)
        key = f"prime_nick:antiflood:{user.id}"
        locked = await self.redis.set(key, "1", nx=True, px=self.ttl_ms)
        if not locked:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком быстро", show_alert=False)
            elif isinstance(event, Message):
                await event.answer(ANTIFLOOD)
            return None
        return await handler(event, data)
