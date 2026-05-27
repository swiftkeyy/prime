from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, LinkPreviewOptions

from config import Settings
from keyboards.main import back_home
from texts import rules

router = Router(name="documents")


@router.callback_query(F.data == "docs:open")
async def docs(callback: CallbackQuery, settings: Settings) -> None:
    await callback.message.edit_text(
        rules(settings),
        reply_markup=back_home(),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await callback.answer()
