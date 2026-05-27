from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("prime_nick.update")


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        try:
            result = await handler(event, data)
            if user:
                logger.info("handled update from user=%s", user.id)
            return result
        except Exception:
            if user:
                logger.exception("update failed user=%s", user.id)
            else:
                logger.exception("update failed")
            raise
