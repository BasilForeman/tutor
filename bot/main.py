import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
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
from bot.handlers.finance_adjustments import router as finance_adjustments_router
from bot.storage.postgres_fsm import PostgresFSMStorage
from bot.services.debt_reminders import debt_reminder_loop, reminder_configuration
from bot.handlers.sheets import router as sheets_router
from bot.integrations.google_sheets import sync_loop
from bot.handlers.analytics import router as analytics_router

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

async def main():
    load_dotenv()

    token = os.getenv("BOT_TOKEN")
    admin_id = os.getenv("ADMIN_ID")

    if not token:
        raise ValueError("BOT_TOKEN не найден в .env")

    if not admin_id:
        raise ValueError("ADMIN_ID не найден в .env")

    bot = Bot(token=token)
    storage_kind = os.getenv("FSM_STORAGE", "postgres").strip().lower()
    if storage_kind == "postgres":
        storage = PostgresFSMStorage()
    elif storage_kind == "memory":
        storage = MemoryStorage()
        logger.warning("FSM_STORAGE=memory: active forms are lost when the bot restarts")
    else:
        raise ValueError("FSM_STORAGE должен быть postgres или memory")

    dp = Dispatcher(storage=storage, events_isolation=SimpleEventIsolation())

    dp.message.filter(is_admin)

    dp.include_router(start_router)
    dp.include_router(tutors_router)
    dp.include_router(clients_router)
    dp.include_router(lead_sources_router)
    dp.include_router(leads_router)
    dp.include_router(assignments_router)
    dp.include_router(payments_router)
    dp.include_router(lessons_router)
    dp.include_router(finance_adjustments_router)
    dp.include_router(sheets_router)
    dp.include_router(analytics_router)

    @dp.errors()
    async def handle_update_error(event: ErrorEvent):
        logger.exception(
            "Unhandled Telegram update error",
            exc_info=event.exception,
        )
        if event.update.message:
            try:
                await event.update.message.answer(
                    "Не удалось обработать запрос. Проверь запись перед повтором операции."
                )
            except Exception:
                logger.error("Unable to send the update error notice")
        return True

    reminder_task = None
    if os.getenv("DEBT_REMINDERS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}:
        reminder_configuration()  # fail early for invalid timezone or schedule
        reminder_task = asyncio.create_task(debt_reminder_loop(bot), name="daily-debt-reminders")

    sheets_task = None
    if os.getenv("GOOGLE_SHEETS_SYNC_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}:
        try:
            interval = int(os.getenv("GOOGLE_SHEETS_SYNC_INTERVAL", "300"))
        except ValueError as exc:
            raise ValueError("GOOGLE_SHEETS_SYNC_INTERVAL должен быть целым числом секунд") from exc
        sheets_task = asyncio.create_task(sync_loop(interval), name="google-sheets-sync")

    print("Bot is running...")

    try:
        await dp.start_polling(bot)
    finally:
        if reminder_task:
            reminder_task.cancel()
            await asyncio.gather(reminder_task, return_exceptions=True)
        if sheets_task:
            sheets_task.cancel()
            await asyncio.gather(sheets_task, return_exceptions=True)
        await dp.storage.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
