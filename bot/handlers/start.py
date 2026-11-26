from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.keyboards.main_menu import get_main_menu

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        text=(
            "Hi, bitch! 👋\n\n"
            "Это единая точка входа для дальнейшего сбора и анализа статистики.\n"
            "Здесь я планирую реализовать анкеты, а после внедрить ИИшку для ГСок.\n"
            "Сейчас ты сможешь:\n\n"
            "👨‍🏫 Учитывать репетиторов\n"
            "👨‍🎓 Вести базу учеников\n"
            "➕ Фиксировать новые передачи\n"
            "💰 Контролировать комиссии и платежи\n\n"
            "Выбери нужный раздел:"
        ),
        reply_markup=get_main_menu()
    )