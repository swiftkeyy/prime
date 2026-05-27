from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from texts import UNKNOWN_ERROR

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.error()
async def global_error(event: ErrorEvent) -> bool:
    logger.exception("unhandled aiogram error", exc_info=event.exception)
    update = event.update
    try:
        if update.callback_query:
            await update.callback_query.answer("Ошибка", show_alert=False)
            if update.callback_query.message:
                await update.callback_query.message.answer(UNKNOWN_ERROR)
        elif update.message:
            await update.message.answer(UNKNOWN_ERROR)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not send error message: %s", exc.__class__.__name__)
    return True
