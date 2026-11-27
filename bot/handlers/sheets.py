import logging

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.filters import is_admin
from bot.integrations.google_sheets import sync_all

router = Router()
router.message.filter(is_admin)
logger = logging.getLogger(__name__)


@router.message(lambda message: message.text == "📊 Синхронизировать Sheets")
async def sync_sheets(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Синхронизирую данные PostgreSQL в Google Sheets…")
    try:
        await sync_all()
    except Exception:
        logger.exception("Manual Sheets sync failed")
        await message.answer("Синхронизация не завершилась. Ошибка записана, автоматическая попытка повторится.")
        return
    await message.answer("Google Sheets обновлён.")
