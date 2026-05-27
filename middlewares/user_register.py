from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

from config import Settings
from database.queries import get_or_create_user


def extract_start_payload(event: TelegramObject) -> str | None:
    if not isinstance(event, Message) or not event.text:
        return None
    parts = event.text.strip().split(maxsplit=1)
    if not parts or not parts[0].startswith("/start"):
        return None
    return parts[1].strip() if len(parts) > 1 else None


class UserRegisterMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker, settings: Settings) -> None:
        self.sessionmaker = sessionmaker
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            data["start_payload"] = extract_start_payload(event)
            tg_user = data.get("event_from_user")
            if tg_user:
                current_user, created = await get_or_create_user(session, tg_user, self.settings)
                data["current_user"] = current_user
                data["is_new_user"] = created
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise
