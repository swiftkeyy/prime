from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, LinkPreviewOptions

from config import Settings
from keyboards.main import back_home
from texts import rules
from utils.telegram import safe_callback_answer, safe_edit_callback

router = Router(name="documents")


@router.callback_query(F.data == "docs:open")
async def docs(callback: CallbackQuery, settings: Settings) -> None:
    await safe_edit_callback(
        callback,
        rules(settings),
        reply_markup=back_home(),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await safe_callback_answer(callback)
