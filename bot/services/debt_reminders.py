import asyncio
import logging
import os
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy import text

from bot.database.connection import async_session
from bot.filters import get_admin_ids

logger = logging.getLogger(__name__)


def reminder_configuration() -> tuple[ZoneInfo, time]:
    timezone = ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow"))
    try:
        reminder_time = time.fromisoformat(os.getenv("DEBT_REMINDER_TIME", "10:00").strip())
    except ValueError as error:
        raise ValueError("DEBT_REMINDER_TIME должен быть формата HH:MM") from error
    if reminder_time.tzinfo is not None:
        raise ValueError("DEBT_REMINDER_TIME указывается по локальному TIMEZONE без смещения")
    return timezone, reminder_time


def seconds_until_next_reminder(now: datetime, reminder_time: time) -> float:
    scheduled = now.replace(
        hour=reminder_time.hour, minute=reminder_time.minute,
        second=reminder_time.second, microsecond=0,
    )
    if scheduled <= now:
        scheduled += timedelta(days=1)
    return max(0.0, (scheduled - now).total_seconds())


def format_overdue_message(rows) -> str:
    lines = ["⚠️ Просроченные комиссии:"]
    for row in rows:
        days = max(0, (row["today"] - row["payment_due_date"]).days)
        lines.append(
            f"Передача №{row['assignment_id']}: долг {row['remaining_amount']}, "
            f"просрочка {days} дн. (срок {row['payment_due_date'].isoformat()})"
        )
    return "\n".join(lines)


async def send_daily_debt_reminders(bot: Bot, reminder_date) -> None:
    admin_ids = get_admin_ids()
    if not admin_ids:
        return
    async with async_session() as session:
        result = await session.execute(text("""
            SELECT f.assignment_id, a.payment_due_date, f.remaining_amount
            FROM assignment_finances AS f
            JOIN assignments AS a ON a.id = f.assignment_id
            WHERE f.remaining_amount > 0
              AND a.payment_due_date IS NOT NULL
              AND a.payment_due_date < :reminder_date
            ORDER BY a.payment_due_date, f.assignment_id
        """), {"reminder_date": reminder_date})
        rows = [dict(row, today=reminder_date) for row in result.mappings().all()]
    if not rows:
        return
    message = format_overdue_message(rows[:50])

    for admin_id in admin_ids:
        async with async_session() as session:
            reserved = await session.execute(text("""
                INSERT INTO debt_reminder_log (admin_id, reminder_date)
                VALUES (:admin_id, :reminder_date)
                ON CONFLICT (admin_id, reminder_date) DO NOTHING
                RETURNING admin_id
            """), {"admin_id": admin_id, "reminder_date": reminder_date})
            if not reserved.first():
                await session.rollback()
                continue
            await session.commit()
        try:
            await bot.send_message(admin_id, message)
        except (TelegramBadRequest, TelegramForbiddenError) as error:
            # These are permanent until the admin fixes chat access/configuration.
            logger.warning("Debt reminder cannot be delivered (%s)", type(error).__name__)
        except Exception as error:
            # Release the daily reservation so this reminder can retry after restart.
            async with async_session() as session:
                await session.execute(text("""
                    DELETE FROM debt_reminder_log
                    WHERE admin_id = :admin_id AND reminder_date = :reminder_date
                """), {"admin_id": admin_id, "reminder_date": reminder_date})
                await session.commit()
            logger.warning("Debt reminder delivery failed (%s)", type(error).__name__)
            raise


async def debt_reminder_loop(bot: Bot) -> None:
    timezone, reminder_time = reminder_configuration()
    while True:
        now = datetime.now(timezone)
        await asyncio.sleep(seconds_until_next_reminder(now, reminder_time))
        while True:
            try:
                today = datetime.now(timezone).date()
                await send_daily_debt_reminders(bot, today)
                break
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("Debt reminder run failed (%s)", type(error).__name__)
                await asyncio.sleep(60)
