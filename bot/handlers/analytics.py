from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.connection import async_session
from bot.filters import is_admin
from bot.keyboards.main_menu import get_statistics_menu
from bot.services.analytics import format_analytics, get_analytics, local_today, period_bounds

router = Router()
router.message.filter(is_admin)


async def _send_report(message: Message, state: FSMContext, period: str):
    await state.clear()
    start_date, end_date = period_bounds(period, local_today())
    async with async_session() as session:
        report = await get_analytics(session, start_date, end_date)
    await message.answer(format_analytics(report), reply_markup=get_statistics_menu())


@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message, state: FSMContext):
    await _send_report(message, state, "month")


@router.message(F.text == "📅 Сегодня")
async def statistics_today(message: Message, state: FSMContext):
    await _send_report(message, state, "today")


@router.message(F.text == "📅 7 дней")
async def statistics_last_seven_days(message: Message, state: FSMContext):
    await _send_report(message, state, "7d")


@router.message(F.text == "📅 Этот месяц")
async def statistics_this_month(message: Message, state: FSMContext):
    await _send_report(message, state, "month")


@router.message(F.text == "📅 Прошлый месяц")
async def statistics_previous_month(message: Message, state: FSMContext):
    await _send_report(message, state, "previous_month")
