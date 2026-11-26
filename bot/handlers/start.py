from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        text=(
            "Привет! 👋\n\n"
            "Это бот для учёта учеников, репетиторов, заявок, передач и занятий.\n"
            "Выбери нужный раздел:"
        ),
        reply_markup=get_main_menu()
    )