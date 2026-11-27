from datetime import date, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.connection import async_session
from bot.filters import is_admin
from bot.keyboards.main_menu import get_main_menu
from bot.services.analytics import format_analytics, get_analytics

router = Router()
router.message.filter(is_admin)


@router.message(F.text == "📈 Аналитика")
async def show_analytics(message: Message, state: FSMContext):
    await state.clear()
    end_date = date.today()
    start_date = end_date - timedelta(days=29)
    async with async_session() as session:
        report = await get_analytics(session, start_date, end_date)
    await message.answer(format_analytics(report), reply_markup=get_main_menu())
