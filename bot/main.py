import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers.start import router as start_router
from bot.handlers.tutors import router as tutors_router
from bot.handlers.clients import router as clients_router
from bot.handlers.lead_sources import router as lead_sources_router
from bot.filters import is_admin
from bot.handlers.leads import router as leads_router
from bot.handlers.assignments import router as assignments_router
from bot.handlers.payments import router as payments_router
from bot.handlers.lessons import router as lessons_router

async def main():
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    admin_id = os.getenv("ADMIN_ID")

    if not token:
        raise ValueError("BOT_TOKEN не найден в .env")

    if not admin_id:
        raise ValueError("ADMIN_ID не найден в .env")

    bot = Bot(token=token)
    dp = Dispatcher()

    dp.message.filter(is_admin)

    dp.include_router(start_router)
    dp.include_router(tutors_router)
    dp.include_router(clients_router)
    dp.include_router(lead_sources_router)
    dp.include_router(leads_router)
    dp.include_router(assignments_router)
    dp.include_router(payments_router)
    dp.include_router(lessons_router)

    print("Bot is running...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
