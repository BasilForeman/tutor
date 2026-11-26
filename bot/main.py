import asyncio
import os

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.handlers.start import router
from bot.filters import is_admin


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

    # Проверяем доступ ко всем входящим сообщениям
    dp.message.filter(is_admin)

    dp.include_router(router)

    print("Bot is running...")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())